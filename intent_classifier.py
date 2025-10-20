"""
意图识别神经网络 - 从头训练完整实现
任务：将用户问题映射到对应网址
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import json
import pickle
from collections import Counter
from typing import List, Dict, Tuple
import random
from tqdm import tqdm

# ==================== 1. 数据处理 ====================

class TextVectorizer:
    """文本向量化器"""
    
    def __init__(self, max_features=10000, max_len=50):
        self.max_features = max_features
        self.max_len = max_len
        self.char2idx = {'<PAD>': 0, '<UNK>': 1, '<START>': 2, '<END>': 3}
        self.idx2char = {0: '<PAD>', 1: '<UNK>', 2: '<START>', 3: '<END>'}
        
    def fit(self, texts: List[str]):
        """构建词汇表"""
        char_counter = Counter()
        
        # 统计字符频率
        for text in texts:
            char_counter.update(list(text))
        
        # 选择最常见的字符
        most_common = char_counter.most_common(self.max_features - 4)
        
        # 构建映射
        for idx, (char, _) in enumerate(most_common, start=4):
            self.char2idx[char] = idx
            self.idx2char[idx] = char
            
        print(f"词汇表大小: {len(self.char2idx)}")
        return self
    
    def transform(self, texts: List[str]) -> np.ndarray:
        """将文本转换为索引序列"""
        sequences = []
        
        for text in texts:
            seq = [self.char2idx.get(char, 1) for char in text[:self.max_len-2]]
            # 添加开始和结束标记
            seq = [2] + seq + [3]
            
            # 填充到最大长度
            padding_length = self.max_len - len(seq)
            seq.extend([0] * padding_length)
            sequences.append(seq)
            
        return np.array(sequences)
    
    def save(self, path: str):
        """保存向量化器"""
        with open(path, 'wb') as f:
            pickle.dump(self, f)
    
    @staticmethod
    def load(path: str):
        """加载向量化器"""
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


# ==================== 2. 模型架构 ====================

class IntentClassifier(nn.Module):
    """
    混合架构：CNN + GRU + Attention
    适合处理中短文本的分类任务
    """
    
    def __init__(self, vocab_size, num_classes, embedding_dim=128, 
                 hidden_dim=128, num_filters=100, filter_sizes=[3, 4, 5],
                 dropout_rate=0.5):
        super(IntentClassifier, self).__init__()
        
        # Embedding层
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        
        # CNN分支 - 捕获局部特征
        self.convs = nn.ModuleList([
            nn.Conv1d(embedding_dim, num_filters, kernel_size=fs, padding=fs//2)
            for fs in filter_sizes
        ])
        
        # GRU分支 - 捕获序列特征
        self.gru = nn.GRU(embedding_dim, hidden_dim, batch_first=True, 
                         bidirectional=True, dropout=dropout_rate if dropout_rate > 0 else 0)
        
        # Attention机制
        self.attention = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1)
        )
        
        # 特征融合
        self.dropout = nn.Dropout(dropout_rate)
        
        # 分类头
        cnn_output_dim = len(filter_sizes) * num_filters
        rnn_output_dim = hidden_dim * 2
        self.classifier = nn.Sequential(
            nn.Linear(cnn_output_dim + rnn_output_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(hidden_dim, num_classes)
        )
        
    def forward(self, x):
        """
        x: [batch_size, seq_len]
        """
        # Embedding
        embedded = self.embedding(x)  # [batch_size, seq_len, embedding_dim]
        
        # CNN分支
        embedded_cnn = embedded.permute(0, 2, 1)  # [batch_size, embedding_dim, seq_len]
        cnn_features = []
        for conv in self.convs:
            conv_out = torch.relu(conv(embedded_cnn))  # [batch_size, num_filters, seq_len]
            pooled = torch.max(conv_out, dim=2)[0]  # [batch_size, num_filters]
            cnn_features.append(pooled)
        cnn_out = torch.cat(cnn_features, dim=1)  # [batch_size, total_num_filters]
        
        # GRU分支
        gru_out, _ = self.gru(embedded)  # [batch_size, seq_len, hidden_dim*2]
        
        # Attention
        attention_weights = self.attention(gru_out)  # [batch_size, seq_len, 1]
        attention_weights = torch.softmax(attention_weights, dim=1)
        rnn_out = torch.sum(gru_out * attention_weights, dim=1)  # [batch_size, hidden_dim*2]
        
        # 特征融合
        combined = torch.cat([cnn_out, rnn_out], dim=1)
        combined = self.dropout(combined)
        
        # 分类
        output = self.classifier(combined)
        
        return output


class SimpleCNN(nn.Module):
    """轻量级CNN模型（备选方案）"""
    
    def __init__(self, vocab_size, num_classes, embedding_dim=64, 
                 num_filters=64, filter_sizes=[3, 4, 5], dropout_rate=0.3):
        super(SimpleCNN, self).__init__()
        
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        
        self.convs = nn.ModuleList([
            nn.Sequential(
                nn.Conv1d(embedding_dim, num_filters, kernel_size=fs),
                nn.BatchNorm1d(num_filters),
                nn.ReLU(),
                nn.MaxPool1d(2)
            )
            for fs in filter_sizes
        ])
        
        self.dropout = nn.Dropout(dropout_rate)
        self.fc = nn.Linear(len(filter_sizes) * num_filters, num_classes)
        
    def forward(self, x):
        x = self.embedding(x)
        x = x.permute(0, 2, 1)
        
        conv_outputs = []
        for conv in self.convs:
            conv_out = conv(x)
            conv_out = torch.max(conv_out, dim=2)[0]
            conv_outputs.append(conv_out)
        
        x = torch.cat(conv_outputs, dim=1)
        x = self.dropout(x)
        x = self.fc(x)
        
        return x


# ==================== 3. 训练器 ====================

class Trainer:
    """模型训练器"""
    
    def __init__(self, model, device='cuda' if torch.cuda.is_available() else 'cpu'):
        self.model = model.to(device)
        self.device = device
        self.best_model_state = None
        
    def train(self, train_loader, val_loader, num_epochs=50, 
              learning_rate=0.001, patience=10):
        """训练模型"""
        
        # 损失函数和优化器
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', patience=patience//2, factor=0.5
        )
        
        # 训练历史
        history = {'train_loss': [], 'train_acc': [], 'val_loss': [], 'val_acc': []}
        
        # 早停
        best_val_loss = float('inf')
        patience_counter = 0
        
        for epoch in range(num_epochs):
            # 训练阶段
            self.model.train()
            train_loss = 0
            train_correct = 0
            train_total = 0
            
            train_bar = tqdm(train_loader, desc=f'Epoch {epoch+1}/{num_epochs} [Train]')
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
                
                train_bar.set_postfix({'loss': loss.item(), 
                                      'acc': train_correct/train_total})
            
            # 验证阶段
            self.model.eval()
            val_loss = 0
            val_correct = 0
            val_total = 0
            
            with torch.no_grad():
                val_bar = tqdm(val_loader, desc=f'Epoch {epoch+1}/{num_epochs} [Val]')
                for inputs, labels in val_bar:
                    inputs, labels = inputs.to(self.device), labels.to(self.device)
                    
                    outputs = self.model(inputs)
                    loss = criterion(outputs, labels)
                    
                    val_loss += loss.item()
                    _, predicted = torch.max(outputs.data, 1)
                    val_total += labels.size(0)
                    val_correct += (predicted == labels).sum().item()
                    
                    val_bar.set_postfix({'loss': loss.item(), 
                                        'acc': val_correct/val_total})
            
            # 计算平均指标
            avg_train_loss = train_loss / len(train_loader)
            avg_val_loss = val_loss / len(val_loader)
            train_acc = train_correct / train_total
            val_acc = val_correct / val_total
            
            # 记录历史
            history['train_loss'].append(avg_train_loss)
            history['train_acc'].append(train_acc)
            history['val_loss'].append(avg_val_loss)
            history['val_acc'].append(val_acc)
            
            # 学习率调整
            scheduler.step(avg_val_loss)
            
            # 保存最佳模型
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                self.best_model_state = self.model.state_dict().copy()
                patience_counter = 0
                print(f'✓ 最佳模型已保存 (val_loss: {avg_val_loss:.4f})')
            else:
                patience_counter += 1
            
            # 打印epoch总结
            print(f'Epoch {epoch+1}: train_loss={avg_train_loss:.4f}, '
                  f'train_acc={train_acc:.4f}, val_loss={avg_val_loss:.4f}, '
                  f'val_acc={val_acc:.4f}')
            
            # 早停
            if patience_counter >= patience:
                print(f'早停: 验证损失已经{patience}轮没有改善')
                break
            
            print('-' * 60)
        
        # 加载最佳模型
        if self.best_model_state:
            self.model.load_state_dict(self.best_model_state)
        
        return history
    
    def save_model(self, path: str):
        """保存模型"""
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'model_config': {
                'vocab_size': self.model.embedding.num_embeddings,
                'num_classes': self.model.classifier[-1].out_features
            }
        }, path)
        print(f'模型已保存到 {path}')


# ==================== 4. 推理引擎 ====================

class IntentPredictor:
    """意图预测器"""
    
    def __init__(self, model_path: str, vectorizer_path: str, 
                 label_map_path: str):
        """
        Args:
            model_path: 模型文件路径
            vectorizer_path: 向量化器文件路径
            label_map_path: 标签映射文件路径
        """
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 加载向量化器
        self.vectorizer = TextVectorizer.load(vectorizer_path)
        
        # 加载标签映射
        with open(label_map_path, 'r', encoding='utf-8') as f:
            self.label_map = json.load(f)
        self.idx_to_url = {int(k): v for k, v in self.label_map.items()}
        
        # 加载模型
        checkpoint = torch.load(model_path, map_location=self.device)
        config = checkpoint['model_config']
        
        self.model = IntentClassifier(
            vocab_size=config['vocab_size'],
            num_classes=config['num_classes']
        )
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.to(self.device)
        self.model.eval()
        
    def predict(self, text: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        预测文本意图
        
        Args:
            text: 输入文本
            top_k: 返回top-k个结果
            
        Returns:
            [(url, confidence), ...]
        """
        # 文本向量化
        sequence = self.vectorizer.transform([text])
        inputs = torch.LongTensor(sequence).to(self.device)
        
        # 预测
        with torch.no_grad():
            outputs = self.model(inputs)
            probabilities = torch.softmax(outputs, dim=1)
            
            # 获取top-k
            top_probs, top_indices = torch.topk(probabilities[0], min(top_k, len(self.idx_to_url)))
            
            results = []
            for prob, idx in zip(top_probs.cpu().numpy(), top_indices.cpu().numpy()):
                url = self.idx_to_url.get(int(idx), "unknown")
                results.append((url, float(prob)))
        
        return results


# ==================== 5. 主训练脚本 ====================

def prepare_data(data_file: str, test_split: float = 0.2):
    """准备训练数据"""
    
    # 加载数据
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 随机打乱
    random.shuffle(data)
    
    # 提取文本和标签
    texts = [item['text'] for item in data]
    urls = [item['url'] for item in data]
    
    # 创建URL到索引的映射
    unique_urls = list(set(urls))
    url_to_idx = {url: idx for idx, url in enumerate(unique_urls)}
    idx_to_url = {idx: url for url, idx in url_to_idx.items()}
    
    # 转换标签
    labels = [url_to_idx[url] for url in urls]
    
    # 划分训练集和测试集
    split_idx = int(len(texts) * (1 - test_split))
    train_texts = texts[:split_idx]
    train_labels = labels[:split_idx]
    test_texts = texts[split_idx:]
    test_labels = labels[split_idx:]
    
    # 创建向量化器
    vectorizer = TextVectorizer(max_features=5000, max_len=50)
    vectorizer.fit(train_texts)
    
    # 向量化文本
    train_sequences = vectorizer.transform(train_texts)
    test_sequences = vectorizer.transform(test_texts)
    
    print(f"训练集大小: {len(train_texts)}")
    print(f"测试集大小: {len(test_texts)}")
    print(f"类别数量: {len(unique_urls)}")
    
    return (train_sequences, train_labels, 
            test_sequences, test_labels,
            vectorizer, idx_to_url)


def main():
    """主函数：完整的训练流程"""
    
    # ========== 配置参数 ==========
    config = {
        'data_file': 'training_data.json',  # 训练数据文件
        'batch_size': 64,
        'num_epochs': 10,
        'learning_rate': 0.001,
        'test_split': 0.2,
        'model_type': 'complex',  # 'complex' 或 'simple'
    }
    
    print("="*60)
    print("开始训练意图识别模型")
    print("="*60)
    
    # ========== 1. 准备数据 ==========
    print("\n1. 准备数据...")
    train_seq, train_labels, test_seq, test_labels, vectorizer, idx_to_url = \
        prepare_data(config['data_file'], config['test_split'])
    
    # 创建数据加载器
    train_dataset = IntentDataset(train_seq, train_labels)
    test_dataset = IntentDataset(test_seq, test_labels)
    
    train_loader = DataLoader(train_dataset, batch_size=config['batch_size'], 
                            shuffle=True, num_workers=2)
    val_loader = DataLoader(test_dataset, batch_size=config['batch_size'], 
                          shuffle=False, num_workers=2)
    
    # ========== 2. 创建模型 ==========
    print("\n2. 创建模型...")
    vocab_size = len(vectorizer.char2idx)
    num_classes = len(idx_to_url)
    
    if config['model_type'] == 'complex':
        model = IntentClassifier(vocab_size, num_classes)
    else:
        model = SimpleCNN(vocab_size, num_classes)
    
    print(f"模型参数量: {sum(p.numel() for p in model.parameters()):,}")
    
    # ========== 3. 训练模型 ==========
    print("\n3. 开始训练...")
    trainer = Trainer(model)
    history = trainer.train(train_loader, val_loader, 
                           num_epochs=config['num_epochs'],
                           learning_rate=config['learning_rate'])
    
    # ========== 4. 保存模型 ==========
    print("\n4. 保存模型...")
    trainer.save_model('intent_model.pth')
    vectorizer.save('vectorizer.pkl')
    
    with open('label_map.json', 'w', encoding='utf-8') as f:
        json.dump(idx_to_url, f, ensure_ascii=False, indent=2)
    
    # ========== 5. 测试模型 ==========
    print("\n5. 测试模型...")
    predictor = IntentPredictor('intent_model.pth', 'vectorizer.pkl', 'label_map.json')
    
    test_queries = [
        "Python怎么处理异常",
        "附近的咖啡店",
        "今天的新闻",
        "如何学习机器学习"
    ]
    
    for query in test_queries:
        results = predictor.predict(query, top_k=3)
        print(f"\n查询: {query}")
        for url, conf in results:
            print(f"  {url}: {conf:.3f}")
    
    print("\n训练完成！")
    
    # ========== 6. 绘制训练曲线 ==========
    import matplotlib.pyplot as plt
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    
    # 损失曲线
    axes[0].plot(history['train_loss'], label='Train Loss')
    axes[0].plot(history['val_loss'], label='Val Loss')
    axes[0].set_xlabel('Epoch')
    axes[0].set_ylabel('Loss')
    axes[0].set_title('训练/验证损失')
    axes[0].legend()
    axes[0].grid(True)
    
    # 准确率曲线
    axes[1].plot(history['train_acc'], label='Train Acc')
    axes[1].plot(history['val_acc'], label='Val Acc')
    axes[1].set_xlabel('Epoch')
    axes[1].set_ylabel('Accuracy')
    axes[1].set_title('训练/验证准确率')
    axes[1].legend()
    axes[1].grid(True)
    
    plt.tight_layout()
    plt.savefig('training_history.png')
    print("\n训练曲线已保存到 training_history.png")


# ==================== 6. 数据生成工具 ==========

def generate_training_data(output_file: str = 'training_data.json'):
    """生成训练数据的示例"""
    import random
    
    # 简化的数据生成
    url_mapping = {
        'code': 'https://www.deepseek.com/',
        'map': 'https://ditu.amap.com/',
        'news': 'https://news.sina.com.cn/',
        'shopping': 'https://www.taobao.com/',
        'video': 'https://www.bilibili.com/',
    }
    
    training_data = []
    
    # 简单的问题示例
    samples = {
        'code': ['Python怎么写', 'JavaScript错误', '调试代码', '算法优化'],
        'map': ['附近咖啡店', '导航回家', '最近的地铁站', '去机场'],
        'news': ['今日新闻', '财经消息', '体育赛事', '国际动态'],
        'shopping': ['买手机', '打折商品', '购物推荐', '价格比较'],
        'video': ['热门视频', '电影推荐', '动漫更新', '直播内容']
    }
    
    # 为每个类别生成数据
    for category, url in url_mapping.items():
        for _ in range(100):  # 每个类别100条
            text = random.choice(samples[category])
            # 添加随机变化
            if random.random() < 0.5:
                text = text + "？"
            training_data.append({'text': text, 'url': url})
    
    # 保存数据
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(training_data, f, ensure_ascii=False, indent=2)
    
    print(f"生成了 {len(training_data)} 条训练数据")
    print(f"数据已保存到 {output_file}")

if __name__ == "__main__":
    # 如果没有训练数据，先生成
    import os
    if not os.path.exists('training_data.json'):
        print("未找到训练数据，正在生成示例数据...")
        generate_training_data()
    
    # 开始训练
    main()