"""
intent_api.py - 意图识别API封装，支持大模型Function Calling
"""

import json
import logging
from typing import Dict, List, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import os

# 导入所有必要的类以解决 pickle 反序列化问题
from train_with_new_data import (
    DynamicIntentPredictor,
    TextVectorizer,
    IntentClassifierV2,
    Config
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 数据模型 ====================

class ConfidenceLevel(Enum):
    """置信度级别"""
    HIGH = "high"        # >80%
    MEDIUM = "medium"    # 50-80%
    LOW = "low"          # <50%

@dataclass
class IntentResult:
    """意图识别结果"""
    query: str                    # 原始查询
    category: str                  # 预测类别
    url: str                      # 推荐URL
    confidence: float             # 置信度（0-1）
    confidence_level: str         # 置信度级别
    alternative_urls: List[Dict]  # 备选URLs
    need_confirmation: bool       # 是否需要确认

    def to_dict(self):
        """转换为字典（用于JSON序列化）"""
        return asdict(self)


# ==================== API接口类 ====================

class IntentRecognitionAPI:
    """
    意图识别API - 可集成到大模型Function Calling
    
    使用示例：
    ```python
    api = IntentRecognitionAPI()
    result = api.recognize_intent("Python教程")
    print(result['url'])  # https://stackoverflow.com/
    ```
    """
    
    def __init__(self, 
                 model_path: str = "intent_model_v2.pth",
                 vectorizer_path: str = "vectorizer_v2.pkl",
                 category_map_path: str = "category_map.json",
                 url_config_path: str = "url_config.json",
                 confidence_threshold: float = 0.7):
        """
        初始化API
        
        Args:
            model_path: 模型文件路径
            vectorizer_path: 向量化器路径
            category_map_path: 类别映射路径
            url_config_path: URL配置路径
            confidence_threshold: 置信度阈值（低于此值需确认）
        """
        self.confidence_threshold = confidence_threshold
        
        # 延迟加载模型（第一次调用时加载）
        self._predictor = None
        self.model_path = model_path
        self.vectorizer_path = vectorizer_path
        self.category_map_path = category_map_path
        self.url_config_path = url_config_path
        
        # 类别中文名映射
        self.category_names = {
            'stock_cn': '股票查询',
            'company_cn': '企业信息',
            'gov_cn': '政府服务',
            'crypto': '加密货币',
            'programming': '编程技术',
            'academic': '学术研究',
            'video': '视频娱乐',
            'life': '生活服务',
            'health': '健康医疗',
            'travel': '旅游出行'
        }
    
    @property
    def predictor(self):
        """懒加载预测器"""
        if self._predictor is None:
            logger.info("加载意图识别模型...")
            self._predictor = DynamicIntentPredictor(
                self.model_path,
                self.vectorizer_path,
                self.category_map_path,
                self.url_config_path
            )
            logger.info("模型加载完成")
        return self._predictor
    
    def recognize_intent(self, 
                        query: str,
                        top_k: int = 3,
                        return_details: bool = True) -> Dict:
        """
        识别用户查询意图并返回对应URL
        
        这是主要的API接口，可以被大模型通过Function Calling调用
        
        Args:
            query: 用户查询文本
            top_k: 返回top-k个可能的结果
            return_details: 是否返回详细信息
            
        Returns:
            包含意图识别结果的字典
            
        Example:
            >>> api.recognize_intent("Python教程")
            {
                'status': 'success',
                'query': 'Python教程',
                'result': {
                    'category': 'programming',
                    'category_name': '编程技术',
                    'url': 'https://stackoverflow.com/',
                    'confidence': 0.92,
                    'confidence_level': 'high',
                    'need_confirmation': False
                },
                'alternatives': [...],
                'message': '已识别为编程技术查询，推荐访问StackOverflow'
            }
        """
        try:
            # 输入验证
            if not query or not query.strip():
                return self._error_response("查询不能为空")
            
            query = query.strip()
            
            # 调用模型预测
            predictions = self.predictor.predict(query, top_k=top_k)
            
            if not predictions:
                return self._error_response("无法识别查询意图")
            
            # 解析主要结果
            main_cat, main_url, main_conf = predictions[0]
            
            # 判断置信度级别
            if main_conf >= 0.8:
                conf_level = ConfidenceLevel.HIGH.value
                need_confirmation = False
            elif main_conf >= 0.5:
                conf_level = ConfidenceLevel.MEDIUM.value
                need_confirmation = main_conf < self.confidence_threshold
            else:
                conf_level = ConfidenceLevel.LOW.value
                need_confirmation = True
            
            # 构建结果
            result = {
                'category': main_cat,
                'category_name': self.category_names.get(main_cat, main_cat),
                'url': main_url,
                'confidence': round(main_conf, 3),
                'confidence_level': conf_level,
                'need_confirmation': need_confirmation
            }
            
            # 添加备选结果
            alternatives = []
            for cat, url, conf in predictions[1:]:
                alternatives.append({
                    'category': cat,
                    'category_name': self.category_names.get(cat, cat),
                    'url': url,
                    'confidence': round(conf, 3)
                })
            
            # 生成消息
            if conf_level == ConfidenceLevel.HIGH.value:
                message = f"已识别为{result['category_name']}查询，推荐访问{self._get_site_name(main_url)}"
            elif conf_level == ConfidenceLevel.MEDIUM.value:
                message = f"可能是{result['category_name']}查询，建议访问{self._get_site_name(main_url)}"
            else:
                message = "查询意图不够明确，请提供更具体的信息"
            
            # 构建返回值
            response = {
                'status': 'success',
                'query': query,
                'result': result,
                'alternatives': alternatives,
                'message': message
            }
            
            # 如果不需要详细信息，简化返回
            if not return_details:
                response = {
                    'status': 'success',
                    'url': main_url,
                    'confidence': round(main_conf, 3)
                }
            
            return response
            
        except Exception as e:
            logger.error(f"识别意图时发生错误: {str(e)}")
            return self._error_response(f"处理失败: {str(e)}")
    
    def batch_recognize(self, queries: List[str]) -> List[Dict]:
        """
        批量识别意图
        
        Args:
            queries: 查询列表
            
        Returns:
            结果列表
        """
        results = []
        for query in queries:
            result = self.recognize_intent(query, return_details=False)
            results.append(result)
        return results
    
    def update_url_mapping(self, category: str, new_url: str) -> Dict:
        """
        动态更新URL映射
        
        Args:
            category: 类别名称
            new_url: 新的URL
            
        Returns:
            操作结果
        """
        try:
            self.predictor.update_url(category, new_url)
            return {
                'status': 'success',
                'message': f'已更新{category}的URL为{new_url}'
            }
        except Exception as e:
            return self._error_response(f"更新失败: {str(e)}")
    
    def get_categories(self) -> Dict:
        """
        获取所有支持的类别
        
        Returns:
            类别信息
        """
        categories = []
        for cat_id, cat_name in self.category_names.items():
            url = self.predictor.url_config.get(cat_id, '')
            categories.append({
                'id': cat_id,
                'name': cat_name,
                'url': url
            })
        
        return {
            'status': 'success',
            'categories': categories
        }
    
    def _get_site_name(self, url: str) -> str:
        """从URL提取站点名称"""
        if '//' in url:
            site = url.split('//')[1].split('/')[0]
            return site.replace('www.', '')
        return url
    
    def _error_response(self, message: str) -> Dict:
        """生成错误响应"""
        return {
            'status': 'error',
            'message': message,
            'result': None
        }


# ==================== Function Calling 接口 ====================

def get_function_schema():
    """
    获取Function Calling的Schema定义
    用于OpenAI API、Anthropic Claude等大模型
    """
    return {
        "name": "recognize_intent",
        "description": "识别用户查询意图并返回最合适的网站URL",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户的查询文本，例如'Python教程'、'贵州茅台股票'等"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回top-k个可能的结果，默认3",
                    "default": 3
                },
                "return_details": {
                    "type": "boolean",
                    "description": "是否返回详细信息，默认true",
                    "default": True
                }
            },
            "required": ["query"]
        }
    }


# ==================== 简化的函数接口（直接调用） ====================

# 全局API实例（单例模式）
_api_instance = None

def get_intent_url(query: str, confidence_threshold: float = 0.7) -> Dict:
    """
    简化的接口函数，直接调用获取URL
    
    这个函数可以直接被大模型调用，无需实例化类
    
    Args:
        query: 用户查询
        confidence_threshold: 置信度阈值
        
    Returns:
        {
            'url': 'https://...',
            'confidence': 0.95,
            'need_confirmation': False,
            'message': '...'
        }
    """
    global _api_instance
    
    # 懒加载API实例
    if _api_instance is None:
        _api_instance = IntentRecognitionAPI(confidence_threshold=confidence_threshold)
    
    # 调用API
    result = _api_instance.recognize_intent(query, return_details=False)
    
    # 简化返回
    if result['status'] == 'success':
        return {
            'url': result['url'],
            'confidence': result['confidence'],
            'need_confirmation': result['confidence'] < confidence_threshold,
            'message': f"推荐访问: {result['url']}"
        }
    else:
        return {
            'url': None,
            'confidence': 0.0,
            'need_confirmation': True,
            'message': result['message']
        }


# ==================== 集成示例 ====================

class IntentFunctionCallingExample:
    """
    展示如何集成到大模型的Function Calling
    """
    
    @staticmethod
    def openai_integration_example():
        """
        OpenAI GPT Function Calling集成示例
        """
        example_code = """
import openai
from intent_api import get_function_schema, get_intent_url

# 定义function
functions = [get_function_schema()]

# 用户消息
messages = [
    {"role": "user", "content": "帮我查一下Python教程"}
]

# 调用GPT
response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=messages,
    functions=functions,
    function_call="auto"
)

# 如果GPT决定调用function
if response.choices[0].message.get("function_call"):
    function_call = response.choices[0].message.function_call
    
    if function_call.name == "recognize_intent":
        # 解析参数
        args = json.loads(function_call.arguments)
        
        # 调用我们的意图识别
        result = get_intent_url(args['query'])
        
        # 返回结果给用户
        print(f"为您找到: {result['url']}")
        """
        return example_code
    
    @staticmethod
    def langchain_integration_example():
        """
        LangChain集成示例
        """
        example_code = """
from langchain.tools import Tool
from intent_api import IntentRecognitionAPI

# 初始化API
intent_api = IntentRecognitionAPI()

# 创建Tool
intent_tool = Tool(
    name="Intent Recognition",
    func=lambda q: intent_api.recognize_intent(q, return_details=False),
    description="识别用户查询意图并返回对应的网站URL"
)

# 在Agent中使用
from langchain.agents import initialize_agent
from langchain.llms import OpenAI

llm = OpenAI(temperature=0)
agent = initialize_agent(
    [intent_tool],
    llm,
    agent="zero-shot-react-description",
    verbose=True
)

# 使用
result = agent.run("我想学Python")
        """
        return example_code
    
    @staticmethod
    def fastapi_integration_example():
        """
        FastAPI服务集成示例
        """
        example_code = """
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from intent_api import IntentRecognitionAPI

app = FastAPI()
api = IntentRecognitionAPI()

class IntentRequest(BaseModel):
    query: str
    top_k: int = 3

class IntentResponse(BaseModel):
    url: str
    confidence: float
    category: str
    message: str

@app.post("/recognize_intent", response_model=IntentResponse)
async def recognize_intent(request: IntentRequest):
    try:
        result = api.recognize_intent(
            request.query,
            top_k=request.top_k,
            return_details=False
        )
        
        if result['status'] == 'success':
            return IntentResponse(
                url=result['url'],
                confidence=result['confidence'],
                category=result.get('category', 'unknown'),
                message=f"推荐访问: {result['url']}"
            )
        else:
            raise HTTPException(status_code=400, detail=result['message'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 运行: uvicorn main:app --reload
        """
        return example_code


# ==================== 测试函数 ====================

def test_api():
    """测试API功能"""
    print("🧪 测试意图识别API\n")
    
    # 初始化API
    api = IntentRecognitionAPI()
    
    # 测试查询
    test_queries = [
        "Python怎么学",
        "贵州茅台股票行情",
        "个人所得税计算",
        "比特币价格",
        "北京旅游攻略",
        "",  # 空查询
        "???",  # 模糊查询
    ]
    
    print("="*60)
    print("1. 测试单个查询识别")
    print("="*60)
    
    for query in test_queries:
        print(f"\n查询: '{query}'")
        result = api.recognize_intent(query)
        
        if result['status'] == 'success':
            r = result['result']
            print(f"  类别: {r['category_name']}")
            print(f"  URL: {r['url']}")
            print(f"  置信度: {r['confidence']:.1%}")
            print(f"  需要确认: {r['need_confirmation']}")
        else:
            print(f"  错误: {result['message']}")
    
    print("\n" + "="*60)
    print("2. 测试简化接口")
    print("="*60)
    
    query = "JavaScript教程"
    result = get_intent_url(query)
    print(f"\n查询: {query}")
    print(f"结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    
    print("\n" + "="*60)
    print("3. 测试批量识别")
    print("="*60)
    
    batch_queries = ["Python", "股票", "旅游"]
    results = api.batch_recognize(batch_queries)
    for q, r in zip(batch_queries, results):
        print(f"{q}: {r['url'] if r['status'] == 'success' else 'ERROR'}")
    
    print("\n✅ API测试完成!")


if __name__ == "__main__":
    # 运行测试
    test_api()
    
    # 打印集成示例
    print("\n" + "="*60)
    print("📚 集成示例")
    print("="*60)
    
    example = IntentFunctionCallingExample()
    print("\n### OpenAI GPT集成示例 ###")
    print(example.openai_integration_example())
    
    print("\n### Function Schema ###")
    print(json.dumps(get_function_schema(), indent=2))