"""
train_with_new_data.py - 使用新数据集训练模型，支持动态URL配置
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import json
import pickle
import random
from typing import Dict, List, Tuple
from collections import Counter
from tqdm import tqdm
from sklearn.model_selection import train_test_split

# ==================== 配置类 ====================

class Config:
    """训练配置"""
    # 数据相关
    data_file = 'training_data_v2.json'
    url_config_file = 'url_config.json'
    test_split = 0.2
    val_split = 0.1
    
    # 模型相关
    max_features = 5000  # 词汇表大小
    max_len = 60  # 最大序列长度
    embedding_dim = 128
    hidden_dim = 128
    num_filters = 100
    filter_sizes = [3, 4, 5]
    dropout_rate = 0.5
    
    # 训练相关
    batch_size = 64
    num_epochs = 10
    learning_rate = 0.001
    patience = 15
    
    # 输出文件
    model_file = 'intent_model_v2.pth'
    vectorizer_file = 'vectorizer_v2.pkl'
    category_map_file = 'category_map.json'  # 类别映射，不包含URL


# ==================== 数据处理 ====================

class TextVectorizer:
    """文本向量化器"""
    
    def __init__(self, max_features=5000, max_len=60):
        self.max_features = max_features
        self.max_len = max_len
        self.char2idx = {'<PAD>': 0, '<UNK>': 1, '<START>': 2, '<END>': 3}
        self.idx2char = {0: '<PAD>', 1: '<UNK>', 2: '<START>', 3: '<END>'}
        
    def fit(self, texts: List[str]):
        """构建词汇表"""
        char_counter = Counter()
        
        for text in texts:
            char_counter.update(list(text))
        
        most_common = char_counter.most_common(self.max_features - 4)
        
        for idx, (char, _) in enumerate(most_common, start=4):
            self.char2idx[char] = idx
            self.idx2char[idx] = char
            
        print(f"✅ 词汇表大小: {len(self.char2idx)}")
        return self
    
    def transform(self, texts: List[str]) -> np.ndarray:
        """文本转索引序列"""
        sequences = []
        
        for text in texts:
            seq = [self.char2idx.get(char, 1) for char in text[:self.max_len-2]]
            seq = [2] + seq + [3]  # 添加开始和结束标记
            
            if len(seq) < self.max_len:
                seq = seq + [0] * (self.max_len - len(seq))
            else:
                seq = seq[:self.max_len]
                
            sequences.append(seq)
            
        return np.array(sequences)
    
    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self, f)
    
    @staticmethod
    def load(path: str):
        with open(path, 'rb') as f:
            return pickle.load(f)


class IntentDataset(Dataset):
    """意图识别数据集"""
    
    def __init__(self, sequences, labels):
        self.sequences = torch.LongTensor(sequences)
        self.labels = torch.LongTensor(labels)
        
    def __len__(self):
        return len(self.labels)
    
    def __getitem__(self, idx):
        return self.sequences[idx], self.labels[idx]


# ==================== 模型定义 ====================

class IntentClassifierV2(nn.Module):
    """增强版意图分类器"""
    
    def __init__(self, vocab_size, num_classes, config: Config):
        super(IntentClassifierV2, self).__init__()
        
        # Embedding层（带预训练初始化）
        self.embedding = nn.Embedding(vocab_size, config.embedding_dim, padding_idx=0)
        nn.init.xavier_uniform_(self.embedding.weight[4:])  # 不初始化特殊标记
        
        # CNN分支
        self.convs = nn.ModuleList([
            nn.Sequential(
                nn.Conv1d(config.embedding_dim, config.num_filters, kernel_size=fs),
                nn.BatchNorm1d(config.num_filters),
                nn.ReLU(),
                nn.MaxPool1d(2)
            )
            for fs in config.filter_sizes
        ])
        
        # BiGRU分支
        self.bigru = nn.GRU(
            config.embedding_dim, 
            config.hidden_dim,
            num_layers=2,
            batch_first=True,
            bidirectional=True,
            dropout=config.dropout_rate if config.dropout_rate > 0 else 0
        )
        
        # 注意力机制
        self.attention = nn.Sequential(
            nn.Linear(config.hidden_dim * 2, config.hidden_dim),
            nn.Tanh(),
            nn.Linear(config.hidden_dim, 1, bias=False)
        )
        
        # Dropout
        self.dropout = nn.Dropout(config.dropout_rate)
        
        # 分类器
        cnn_dim = len(config.filter_sizes) * config.num_filters
        gru_dim = config.hidden_dim * 2
        
        self.classifier = nn.Sequential(
            nn.Linear(cnn_dim + gru_dim, config.hidden_dim * 2),
            nn.BatchNorm1d(config.hidden_dim * 2),
            nn.ReLU(),
            nn.Dropout(config.dropout_rate),
            nn.Linear(config.hidden_dim * 2, config.hidden_dim),
            nn.ReLU(),
            nn.Dropout(config.dropout_rate / 2),
            nn.Linear(config.hidden_dim, num_classes)
        )
        
    def forward(self, x):
        # Embedding
        embedded = self.embedding(x)  # [batch, seq_len, emb_dim]
        
        # CNN特征
        embedded_t = embedded.transpose(1, 2)  # [batch, emb_dim, seq_len]
        cnn_features = []
        for conv in self.convs:
            conv_out = conv(embedded_t)
            pooled = torch.max(conv_out, dim=2)[0]
            cnn_features.append(pooled)
        cnn_out = torch.cat(cnn_features, dim=1)
        
        # GRU特征
        gru_out, _ = self.bigru(embedded)  # [batch, seq_len, hidden*2]
        
        # 注意力加权
        att_weights = self.attention(gru_out)  # [batch, seq_len, 1]
        att_weights = torch.softmax(att_weights, dim=1)
        gru_weighted = torch.sum(gru_out * att_weights, dim=1)  # [batch, hidden*2]
        
        # 特征融合
        combined = torch.cat([cnn_out, gru_weighted], dim=1)
        combined = self.dropout(combined)
        
        # 分类
        output = self.classifier(combined)
        
        return output


# ==================== 训练器 ====================

class ModelTrainer:
    """模型训练器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"🖥️ 使用设备: {self.device}")
        
    def prepare_data(self):
        """准备数据"""
        print("\n📊 准备数据...")
        
        # 加载数据
        with open(self.config.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取文本和类别
        texts = [item['text'] for item in data]
        categories = [item['category'] for item in data]
        
        # 创建类别到索引的映射
        unique_categories = sorted(list(set(categories)))
        cat_to_idx = {cat: idx for idx, cat in enumerate(unique_categories)}
        idx_to_cat = {idx: cat for cat, idx in cat_to_idx.items()}
        
        # 保存类别映射（不包含URL）
        with open(self.config.category_map_file, 'w', encoding='utf-8') as f:
            json.dump(idx_to_cat, f, ensure_ascii=False, indent=2)
        
        # 转换类别为索引
        labels = [cat_to_idx[cat] for cat in categories]
        
        # 划分数据集
        X_temp, X_test, y_temp, y_test = train_test_split(
            texts, labels, test_size=self.config.test_split, 
            random_state=42, stratify=labels
        )
        
        X_train, X_val, y_train, y_val = train_test_split(
            X_temp, y_temp, test_size=self.config.val_split,
            random_state=42, stratify=y_temp
        )
        
        print(f"  训练集: {len(X_train)} 样本")
        print(f"  验证集: {len(X_val)} 样本")
        print(f"  测试集: {len(X_test)} 样本")
        print(f"  类别数: {len(unique_categories)}")
        
        # 创建向量化器
        self.vectorizer = TextVectorizer(
            max_features=self.config.max_features,
            max_len=self.config.max_len
        )
        self.vectorizer.fit(X_train)
        
        # 向量化
        train_seq = self.vectorizer.transform(X_train)
        val_seq = self.vectorizer.transform(X_val)
        test_seq = self.vectorizer.transform(X_test)
        
        # 创建数据加载器
        train_dataset = IntentDataset(train_seq, y_train)
        val_dataset = IntentDataset(val_seq, y_val)
        test_dataset = IntentDataset(test_seq, y_test)
        
        self.train_loader = DataLoader(
            train_dataset, batch_size=self.config.batch_size,
            shuffle=True, num_workers=2
        )
        self.val_loader = DataLoader(
            val_dataset, batch_size=self.config.batch_size,
            shuffle=False, num_workers=2
        )
        self.test_loader = DataLoader(
            test_dataset, batch_size=self.config.batch_size,
            shuffle=False, num_workers=2
        )
        
        self.num_classes = len(unique_categories)
        self.vocab_size = len(self.vectorizer.char2idx)
        
        return idx_to_cat
    
    def train(self):
        """训练模型"""
        print("\n🚀 开始训练...")
        
        # 创建模型
        self.model = IntentClassifierV2(
            self.vocab_size, 
            self.num_classes, 
            self.config
        ).to(self.device)
        
        # 打印模型信息
        total_params = sum(p.numel() for p in self.model.parameters())
        print(f"  模型参数量: {total_params:,}")
        
        # 损失函数和优化器
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=self.config.learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', patience=5, factor=0.5
        )
        
        # 训练循环
        best_val_loss = float('inf')
        best_val_acc = 0
        patience_counter = 0
        history = {'train_loss': [], 'val_loss': [], 'train_acc': [], 'val_acc': []}
        
        for epoch in range(self.config.num_epochs):
            # 训练阶段
            self.model.train()
            train_loss = 0
            train_correct = 0
            train_total = 0
            
            train_bar = tqdm(self.train_loader, desc=f'Epoch {epoch+1}/{self.config.num_epochs}')
            for inputs, labels in train_bar:
                inputs, labels = inputs.to(self.device), labels.to(self.device)
                
                optimizer.zero_grad()
                outputs = self.model(inputs)
                loss = criterion(outputs, labels)
                loss.backward()
                
                # 梯度裁剪
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                
                optimizer.step()
                
                train_loss += loss.item()
                _, predicted = torch.max(outputs.data, 1)
                train_total += labels.size(0)
                train_correct += (predicted == labels).sum().item()
                
                train_bar.set_postfix({
                    'loss': f'{loss.item():.4f}',
                    'acc': f'{train_correct/train_total:.4f}'
                })
            
            # 验证阶段
            self.model.eval()
            val_loss = 0
            val_correct = 0
            val_total = 0
            
            with torch.no_grad():
                for inputs, labels in self.val_loader:
                    inputs, labels = inputs.to(self.device), labels.to(self.device)
                    
                    outputs = self.model(inputs)
                    loss = criterion(outputs, labels)
                    
                    val_loss += loss.item()
                    _, predicted = torch.max(outputs.data, 1)
                    val_total += labels.size(0)
                    val_correct += (predicted == labels).sum().item()
            
            # 计算平均指标
            avg_train_loss = train_loss / len(self.train_loader)
            avg_val_loss = val_loss / len(self.val_loader)
            train_acc = train_correct / train_total
            val_acc = val_correct / val_total
            
            # 记录历史
            history['train_loss'].append(avg_train_loss)
            history['val_loss'].append(avg_val_loss)
            history['train_acc'].append(train_acc)
            history['val_acc'].append(val_acc)
            
            # 学习率调整
            scheduler.step(avg_val_loss)
            
            # 保存最佳模型
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_val_loss = avg_val_loss
                self.save_model()
                patience_counter = 0
                print(f"  ✅ 最佳模型已保存 (val_acc: {val_acc:.4f})")
            else:
                patience_counter += 1
            
            # 打印结果
            if (epoch + 1) % 5 == 0 or patience_counter == 0:
                print(f"  Epoch {epoch+1}: "
                      f"train_loss={avg_train_loss:.4f}, train_acc={train_acc:.4f}, "
                      f"val_loss={avg_val_loss:.4f}, val_acc={val_acc:.4f}")
            
            # 早停
            if patience_counter >= self.config.patience:
                print(f"\n⏹️ 早停: 验证准确率已经{self.config.patience}轮没有改善")
                break
        
        print(f"\n🏆 最佳验证准确率: {best_val_acc:.4f}")
        return history
    
    def test(self):
        """测试模型"""
        print("\n🧪 测试模型...")
        
        # 加载最佳模型
        checkpoint = torch.load(self.config.model_file, map_location=self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.eval()
        
        test_correct = 0
        test_total = 0
        
        with torch.no_grad():
            for inputs, labels in tqdm(self.test_loader, desc='Testing'):
                inputs, labels = inputs.to(self.device), labels.to(self.device)
                
                outputs = self.model(inputs)
                _, predicted = torch.max(outputs.data, 1)
                test_total += labels.size(0)
                test_correct += (predicted == labels).sum().item()
        
        test_acc = test_correct / test_total
        print(f"  测试准确率: {test_acc:.4f}")
        
        return test_acc
    
    def save_model(self):
        """保存模型"""
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'model_config': {
                'vocab_size': self.vocab_size,
                'num_classes': self.num_classes,
                'config': self.config.__dict__
            }
        }, self.config.model_file)
        
        # 保存向量化器
        self.vectorizer.save(self.config.vectorizer_file)


# ==================== 预测器（支持动态URL） ====================

class DynamicIntentPredictor:
    """动态意图预测器 - 支持运行时修改URL"""
    
    def __init__(self, model_file='intent_model_v2.pth',
                 vectorizer_file='vectorizer_v2.pkl',
                 category_map_file='category_map.json',
                 url_config_file='url_config.json'):
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 加载向量化器
        self.vectorizer = TextVectorizer.load(vectorizer_file)
        
        # 加载类别映射
        with open(category_map_file, 'r', encoding='utf-8') as f:
            self.idx_to_cat = json.load(f)
            self.idx_to_cat = {int(k): v for k, v in self.idx_to_cat.items()}
        
        # 加载URL配置（可动态修改）
        self.load_url_config(url_config_file)
        
        # 加载模型
        checkpoint = torch.load(model_file, map_location=self.device)
        model_config = checkpoint['model_config']
        config = Config()
        for k, v in model_config.get('config', {}).items():
            setattr(config, k, v)
        
        self.model = IntentClassifierV2(
            model_config['vocab_size'],
            model_config['num_classes'],
            config
        )
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)
        self.model.eval()
        
    def load_url_config(self, url_config_file):
        """加载或重新加载URL配置"""
        with open(url_config_file, 'r', encoding='utf-8') as f:
            self.url_config = json.load(f)
        print(f"✅ URL配置已加载: {url_config_file}")
    
    def predict(self, text: str, top_k: int = 3) -> List[Tuple[str, str, float]]:
        """
        预测文本意图
        返回: [(类别, URL, 置信度), ...]
        """
        # 向量化
        sequence = self.vectorizer.transform([text])
        inputs = torch.LongTensor(sequence).to(self.device)
        
        # 预测
        with torch.no_grad():
            outputs = self.model(inputs)
            probabilities = torch.softmax(outputs, dim=1)
            
            # 获取top-k
            top_probs, top_indices = torch.topk(probabilities[0], min(top_k, len(self.idx_to_cat)))
            
            results = []
            for prob, idx in zip(top_probs.cpu().numpy(), top_indices.cpu().numpy()):
                category = self.idx_to_cat.get(int(idx), "unknown")
                url = self.url_config.get(category, "https://www.google.com/")
                results.append((category, url, float(prob)))
        
        return results
    
    def update_url(self, category: str, new_url: str):
        """动态更新某个类别的URL"""
        if category in self.url_config:
            self.url_config[category] = new_url
            print(f"✅ 已更新 {category} 的URL为: {new_url}")
        else:
            print(f"⚠️ 类别 {category} 不存在")


# ==================== 主函数 ====================

def main():
    """主训练流程"""
    print("="*60)
    print("🚀 意图识别模型训练 V2.0")
    print("="*60)
    
    # 初始化配置
    config = Config()
    trainer = ModelTrainer(config)
    
    # 准备数据
    idx_to_cat = trainer.prepare_data()
    
    # 训练模型
    history = trainer.train()
    
    # 测试模型
    test_acc = trainer.test()
    
    # 快速测试
    print("\n📝 快速测试:")
    predictor = DynamicIntentPredictor()
    
    test_queries = [
        "贵州茅台股票怎么样",
        "字节跳动公司待遇",
        "个人所得税最新政策",
        "比特币今日行情",
        "Python怎么学"
    ]
    
    for query in test_queries:
        results = predictor.predict(query, top_k=2)
        print(f"\n查询: {query}")
        for cat, url, conf in results:
            print(f"  {cat:15s} → {url:30s} (置信度: {conf:.3f})")
    
    print("\n✅ 训练完成!")
    print(f"📁 模型文件: {config.model_file}")
    print(f"📁 向量化器: {config.vectorizer_file}")
    print(f"📁 类别映射: {config.category_map_file}")
    print(f"📁 URL配置: {config.url_config_file}")
    print("\n💡 提示: 您可以随时修改 url_config.json 来更改URL映射，无需重新训练!")


if __name__ == "__main__":
    main()