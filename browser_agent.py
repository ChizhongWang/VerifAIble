"""
浏览器自动化代理
使用 Playwright + 多模态模型自动浏览网页并提取信息
基于视觉标注方案（Set-of-Mark）
"""
import asyncio
import base64
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Literal
import io

from playwright.async_api import async_playwright, Page, Browser
from pydantic import BaseModel, Field
import openai
import hashlib

# 导入PIL用于图像标注
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("警告: 未安装Pillow库，请运行: pip install Pillow")
    Image = ImageDraw = ImageFont = None

logger = logging.getLogger(__name__)


# ========== 任务管理和进度跟踪 ==========

class SubTask(BaseModel):
    """子任务定义（面向状态的检查点）"""
    model_config = {"extra": "forbid"}

    id: int = Field(description="子任务编号")
    description: str = Field(
        description="子任务的目标状态描述（描述期望达成的状态，而不是具体操作步骤）"
    )
    success_criteria: List[str] = Field(
        description="完成条件列表（用于验证目标状态是否达成），例如：['已获得10条公告清单', '每条都有下载链接']"
    )
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending",
        description="子任务状态"
    )
    result: Optional[str] = Field(
        default=None,
        description="子任务执行结果"
    )
    artifacts: List[str] = Field(
        default_factory=list,
        description="产出物列表（如文件路径、URL、数据等），用于追踪任务产出"
    )


class TaskDecomposition(BaseModel):
    """任务拆解结果"""
    model_config = {"extra": "forbid"}

    subtasks: List[SubTask] = Field(
        description="拆解后的子任务列表"
    )


class SubtaskCompletionCheck(BaseModel):
    """子任务完成检查结果"""
    model_config = {"extra": "forbid"}

    completed: bool = Field(
        description="子任务是否已完成"
    )
    reason: str = Field(
        description="完成或未完成的原因"
    )


class TaskManager:
    """任务拆解和进度管理"""

    def __init__(self, client: openai.OpenAI):
        self.client = client
        self.main_task: Optional[str] = None
        self.subtasks: List[SubTask] = []
        self.current_subtask_index: int = 0

    async def decompose_task(self, task_description: str) -> List[SubTask]:
        """
        使用 LLM 将主任务拆解为子任务

        示例：
        输入: "找到并阅读300866股票最新的10条公告，分析总结其中可以为投资者提供哪些未来投资的依据"
        输出: [
            SubTask(id=0, description="导航到深圳证券交易所公告查询页面"),
            SubTask(id=1, description="搜索股票代码300866"),
            SubTask(id=2, description="阅读第1条公告（完整读取PDF内容）"),
            SubTask(id=3, description="返回列表页"),
            SubTask(id=4, description="阅读第2条公告（完整读取PDF内容）"),
            ...
            SubTask(id=21, description="返回列表页"),
            SubTask(id=22, description="分析总结10条公告，提取投资依据"),
        ]
        """
        self.main_task = task_description

        logger.info(f"🎯 开始拆解任务: {task_description}")

        try:
            response = self.client.responses.parse(
                model="gpt-5-mini-2025-08-07",
                input=[
                    {
                        "role": "system",
                        "content": """你是一个任务规划专家。请将用户的任务拆解为**面向状态的检查点**，而不是具体操作步骤。

**核心原则：描述目标状态，而非操作过程**

✅ 正确示例（状态导向）：
- "已找到公告列表页面"
- "已下载所有需要的PDF文件到本地"
- "已完成内容分析并生成报告"

❌ 错误示例（操作导向）：
- "在搜索框输入300866" ← 这是操作步骤，不是状态
- "点击查询按钮" ← 过于具体
- "按日期降序排序" ← 假设了网站结构，可能不需要

**拆解要求**：
1. 每个子任务描述一个**明确的、可验证的状态**（已完成什么、已获得什么）
2. 验证条件要**宽松实用**，不要过于严苛，允许部分完成后继续
3. 子任务数量控制在 2-3 个（简洁为主）
4. 不要假设具体的操作步骤或网站结构
5. 让执行Agent自主决定如何达成目标状态

**示例任务**："找到并下载300866股票最新10条公告的PDF"

**正确拆解**：
```json
{
  "subtasks": [
    {
      "id": 1,
      "description": "已找到300866的公告列表页面",
      "success_criteria": [
        "页面URL或标题包含'公告'、'披露'等关键词",
        "页面中有多条公告标题和日期"
      ]
    },
    {
      "id": 2,
      "description": "已下载至少5条公告PDF到本地",
      "success_criteria": [
        "本地存在至少5个PDF文件",
        "文件名包含公告相关信息"
      ]
    }
  ]
}
```

**重要**：
- 验证条件不要太死板（如"必须恰好10条"），允许"至少N条"这样的弹性标准
- 优先关注**最终可验证的产物**（如本地文件），而不是中间状态
- 如果某个状态"大概率正确"就可以继续，不要过度验证

记住：描述"已达成的状态"，而不是"如何达成"！目标是**实用、可行**，而不是完美！"""
                    },
                    {
                        "role": "user",
                        "content": f"请拆解这个任务：{task_description}"
                    }
                ],
                text_format=TaskDecomposition,
                max_output_tokens=3000,  # 增加空间以包含 success_criteria
            )

            # 获取结构化输出
            decomposition: TaskDecomposition = response.output_parsed
            self.subtasks = decomposition.subtasks
            logger.info(f"✅ 成功拆解为 {len(self.subtasks)} 个子任务")
            return self.subtasks

        except Exception as e:
            logger.error(f"❌ 任务拆解失败: {e}")
            # 降级：创建一个简单的单任务
            self.subtasks = [SubTask(id=0, description=task_description)]
            return self.subtasks

    def get_current_subtask(self) -> Optional[SubTask]:
        """获取当前应该执行的子任务"""
        if self.current_subtask_index < len(self.subtasks):
            return self.subtasks[self.current_subtask_index]
        return None

    def mark_current_subtask_complete(self, result: str = ""):
        """标记当前子任务为完成，并移动到下一个"""
        if self.current_subtask_index < len(self.subtasks):
            self.subtasks[self.current_subtask_index].status = "completed"
            self.subtasks[self.current_subtask_index].result = result

            logger.info(f"✅ 子任务 #{self.current_subtask_index} 完成: {self.subtasks[self.current_subtask_index].description}")
            self.current_subtask_index += 1

    def mark_current_subtask_in_progress(self):
        """标记当前子任务为进行中"""
        if self.current_subtask_index < len(self.subtasks):
            self.subtasks[self.current_subtask_index].status = "in_progress"

    def get_progress_summary(self) -> str:
        """获取任务进度摘要"""
        total = len(self.subtasks)
        completed = sum(1 for task in self.subtasks if task.status == "completed")
        current = self.get_current_subtask()

        summary = f"**任务进度**: {completed}/{total} 已完成\n"
        if current:
            summary += f"**当前任务**: #{current.id} - {current.description}\n"

        # 列出最近完成的3个子任务
        completed_tasks = [t for t in self.subtasks if t.status == "completed"]
        if completed_tasks:
            summary += f"\n**最近完成**:\n"
            for task in completed_tasks[-3:]:
                summary += f"  ✅ #{task.id}: {task.description}\n"

        # 列出接下来的2个子任务
        upcoming = self.subtasks[self.current_subtask_index + 1:self.current_subtask_index + 3]
        if upcoming:
            summary += f"\n**接下来**:\n"
            for task in upcoming:
                summary += f"  ⏭️ #{task.id}: {task.description}\n"

        return summary

    def is_all_complete(self) -> bool:
        """检查是否所有子任务都已完成"""
        return self.current_subtask_index >= len(self.subtasks)

    def export_results(self) -> str:
        """导出所有子任务的结果"""
        output = f"# 任务执行报告\n\n## 主任务\n{self.main_task}\n\n## 子任务详情\n\n"
        for task in self.subtasks:
            output += f"### #{task.id}: {task.description}\n"
            output += f"**状态**: {task.status}\n"
            if task.result:
                output += f"**结果**: {task.result}\n"
            output += "\n"
        return output


# ========== 页面关系图谱 ==========

class PageNode(BaseModel):
    """页面节点"""
    url: str = Field(description="页面URL")
    page_type: Literal["entry", "list", "detail", "other"] = Field(
        default="other",
        description="页面类型"
    )
    title: Optional[str] = Field(default=None, description="页面标题")
    description: Optional[str] = Field(default=None, description="页面描述")
    visited_count: int = Field(default=0, description="访问次数")
    parent_url: Optional[str] = Field(default=None, description="父页面URL（从哪个页面来的）")


class SiteGraph:
    """网站页面关系图谱"""

    def __init__(self):
        self.nodes: Dict[str, PageNode] = {}
        self.current_url: Optional[str] = None
        self.navigation_history: List[str] = []  # URL 历史栈

    def add_or_update_page(
        self,
        url: str,
        page_type: str = "other",
        title: str = None,
        description: str = None,
        parent_url: str = None
    ) -> PageNode:
        """添加或更新页面节点"""
        if url in self.nodes:
            # 更新已有节点
            node = self.nodes[url]
            node.visited_count += 1
            if title:
                node.title = title
            if description:
                node.description = description
        else:
            # 创建新节点
            node = PageNode(
                url=url,
                page_type=page_type,
                title=title,
                description=description,
                parent_url=parent_url or self.current_url
            )
            self.nodes[url] = node
            logger.info(f"🗺️  新页面: {page_type} - {url[:60]}")

        # 更新当前位置
        self.current_url = url

        # 添加到导航历史
        self.navigation_history.append(url)

        return node

    def get_current_page(self) -> Optional[PageNode]:
        """获取当前页面节点"""
        if self.current_url:
            return self.nodes.get(self.current_url)
        return None

    def get_parent_page(self) -> Optional[PageNode]:
        """获取父页面（上一级页面）"""
        current = self.get_current_page()
        if current and current.parent_url:
            return self.nodes.get(current.parent_url)
        return None

    def suggest_back_to_parent(self) -> str:
        """建议如何返回父页面"""
        parent = self.get_parent_page()
        if parent:
            return f"💡 **导航提示**: 当前在详情页，完成阅读后请使用 BACK 操作返回 {parent.page_type} 页（{parent.title or parent.url[:40]}），以便继续下一个任务"
        return ""

    def mark_navigation(self, from_url: str, to_url: str, action: str):
        """记录导航行为（方便理解页面关系）"""
        logger.info(f"📍 导航: {action} - {from_url[:40]} → {to_url[:40]}")

    def get_navigation_context(self) -> str:
        """获取导航上下文信息"""
        current = self.get_current_page()
        if not current:
            return ""

        context = f"**当前页面**: {current.page_type} - {current.title or current.url[:50]}\n"
        context += f"**访问次数**: {current.visited_count}\n"

        # 显示导航路径（最近5步）
        if len(self.navigation_history) > 1:
            path = self.navigation_history[-5:]
            context += f"**导航路径**: "
            for i, url in enumerate(path):
                node = self.nodes.get(url)
                if node:
                    context += f"{node.page_type}"
                    if i < len(path) - 1:
                        context += " → "
            context += "\n"

        # 如果在详情页，提示应该返回
        if current.page_type == "detail":
            parent = self.get_parent_page()
            if parent and parent.page_type == "list":
                context += f"\n💡 **重要提示**: 你现在在详情页，完成当前任务后，应使用 BACK 返回列表页继续下一个任务\n"

        return context


# ========== 批量执行引擎和页面缓存 ==========

class PageSnapshot(BaseModel):
    """页面快照（用于缓存元素信息）"""
    model_config = {"extra": "forbid"}

    url: str
    timestamp: datetime
    elements: List[dict]
    html_hash: str  # 用于检测页面是否变化

    def is_valid(self, current_url: str, current_html_hash: str, max_age_seconds: int = 300) -> bool:
        """检查快照是否仍然有效"""
        # URL必须匹配
        if self.url != current_url:
            return False
        # HTML内容必须相同
        if self.html_hash != current_html_hash:
            return False
        # 不能太旧（默认5分钟）
        age = (datetime.now() - self.timestamp).total_seconds()
        if age > max_age_seconds:
            return False
        return True


class BatchExecutionEngine:
    """批量执行引擎 - 支持新标签页模式和元素缓存"""

    def __init__(self):
        self.execution_count = 0

    async def execute_batch(
        self,
        context,  # Browser context
        list_page: Page,
        element_ids: List[int],
        description: str,
        use_new_tab: bool = True
    ) -> List[dict]:
        """
        批量执行操作序列

        Args:
            context: Browser context (用于创建新标签页)
            list_page: 列表页（保持不变）
            element_ids: 要批量操作的元素ID列表
            description: 操作描述
            use_new_tab: 是否使用新标签页模式（推荐）

        Returns:
            执行结果列表
        """
        logger.info(f"🚀 开始批量执行: {description}")
        logger.info(f"   目标元素: {element_ids}")
        logger.info(f"   模式: {'新标签页' if use_new_tab else '导航返回'}")

        results = []
        total = len(element_ids)

        for idx, element_id in enumerate(element_ids, start=1):
            logger.info(f"📄 批量处理 [{idx}/{total}]: 元素#{element_id}")

            try:
                if use_new_tab:
                    # 新标签页模式：列表页保持不变
                    result = await self._execute_in_new_tab(
                        context, list_page, element_id, idx, total
                    )
                else:
                    # 导航模式：点击 → 提取 → 返回
                    result = await self._execute_with_navigation(
                        list_page, element_id, idx, total
                    )

                results.append({
                    "index": idx,
                    "element_id": element_id,
                    "status": "success",
                    "data": result
                })

            except Exception as e:
                logger.warning(f"⚠️  元素#{element_id}执行失败: {e}")
                results.append({
                    "index": idx,
                    "element_id": element_id,
                    "status": "failed",
                    "error": str(e)
                })

                # 失败率检查
                failure_rate = sum(1 for r in results if r["status"] == "failed") / len(results)
                if failure_rate > 0.3:
                    logger.error(f"❌ 批量执行失败率过高({failure_rate:.0%})，终止")
                    break

            # 轻微延迟，避免反爬
            await asyncio.sleep(0.5)

        success_count = sum(1 for r in results if r["status"] == "success")
        logger.info(f"✅ 批量执行完成: {success_count}/{total} 成功")

        return results

    async def _execute_in_new_tab(
        self,
        context,
        list_page: Page,
        element_id: int,
        index: int,  # noqa: ARG002 - 保留用于日志
        total: int   # noqa: ARG002 - 保留用于日志
    ) -> dict:
        """在新标签页中执行（列表页保持不变）"""
        detail_page = None

        try:
            # 获取目标元素的href
            selector = f'[data-browser-agent-id="ba-{element_id}"]'
            href = await list_page.get_attribute(selector, 'href')

            if href:
                # 方式1: 直接在新标签页打开URL
                detail_page = await context.new_page()
                # 确保URL是绝对路径
                if not href.startswith('http'):
                    from urllib.parse import urljoin
                    href = urljoin(list_page.url, href)
                await detail_page.goto(href, wait_until='networkidle', timeout=15000)
            else:
                # 方式2: 使用Ctrl+Click在新标签页打开
                async with context.expect_page() as new_page_info:
                    # Mac用Meta(Command)，Windows/Linux用Control
                    await list_page.click(selector, modifiers=['Meta'])
                detail_page = await new_page_info.value
                await detail_page.wait_for_load_state('networkidle', timeout=15000)

            # 提取内容
            title = await detail_page.title()
            content = await detail_page.text_content('body')

            # 检查是否有PDF链接
            pdf_links = await detail_page.query_selector_all('a[href$=".pdf"]')
            pdf_urls = []
            for link in pdf_links[:5]:  # 最多记录5个PDF
                url = await link.get_attribute('href')
                if url:
                    pdf_urls.append(url)

            # 关闭详情页
            await detail_page.close()

            return {
                "title": title,
                "content": content[:1000],  # 保存前1000字符
                "pdf_urls": pdf_urls,
                "url": href or detail_page.url
            }

        except Exception as e:
            logger.warning(f"新标签页执行失败: {e}")
            if detail_page:
                await detail_page.close()
            raise

    async def _execute_with_navigation(
        self,
        page: Page,
        element_id: int,
        index: int,  # noqa: ARG002 - 保留用于日志
        total: int   # noqa: ARG002 - 保留用于日志
    ) -> dict:
        """使用导航模式执行（点击 → 提取 → 返回）"""
        try:
            # 点击元素
            selector = f'[data-browser-agent-id="ba-{element_id}"]'
            await page.click(selector)
            await page.wait_for_load_state('networkidle', timeout=10000)

            # 验证页面加载成功
            title = await page.title()
            if "404" in title or "错误" in title:
                raise Exception(f"页面加载失败: {title}")

            # 提取内容
            content = await page.text_content('body')

            # 检查PDF链接
            pdf_links = await page.query_selector_all('a[href$=".pdf"]')
            pdf_urls = []
            for link in pdf_links[:5]:
                url = await link.get_attribute('href')
                if url:
                    pdf_urls.append(url)

            # 返回列表页（关键：这里不重新提取元素，使用缓存）
            await page.go_back()
            await page.wait_for_load_state('networkidle', timeout=5000)

            return {
                "title": title,
                "content": content[:1000],
                "pdf_urls": pdf_urls,
                "url": page.url
            }

        except Exception as e:
            logger.warning(f"导航模式执行失败: {e}")
            # 尝试返回
            try:
                await page.go_back()
                await page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass
            raise


# 定义决策模型（Structured Output - 基于元素ID的视觉标注方案）
class BrowserDecision(BaseModel):
    """浏览器操作决策（视觉标注方案）"""
    model_config = {"extra": "forbid"}

    action: Literal["CLICK", "TYPE", "SCROLL", "BACK", "FORWARD", "REFRESH", "TASK_COMPLETE", "BATCH_EXECUTE", "CHECK_DOWNLOADS"] = Field(
        description="要执行的操作类型"
    )
    reasoning: str = Field(
        description="为什么选择这个操作的原因"
    )
    element_id: Optional[int] = Field(
        default=None,
        description="要操作的元素编号（从标注的截图中选择，用于CLICK和TYPE）"
    )
    text: Optional[str] = Field(
        default=None,
        description="要输入的文本内容（用于TYPE操作）"
    )
    scroll_amount: Optional[int] = Field(
        default=500,
        description="滚动距离（像素），正数向下，负数向上（用于SCROLL操作）"
    )
    summary: Optional[str] = Field(
        default=None,
        description="任务完成时的答案摘要，100-200字（仅用于TASK_COMPLETE）"
    )
    citations: Optional[List[str]] = Field(
        default=None,
        description="需要在报告中高亮显示的原文引用片段列表，每个50-200字（仅用于TASK_COMPLETE）"
    )
    # 批量执行相关字段
    batch_element_ids: Optional[List[int]] = Field(
        default=None,
        description="批量执行的目标元素ID列表（用于BATCH_EXECUTE）"
    )
    batch_description: Optional[str] = Field(
        default=None,
        description="批量操作的描述，如'点击公告并提取内容'（用于BATCH_EXECUTE）"
    )

class BrowserAgent:
    """浏览器自动化代理"""

    def __init__(self, api_key: str, max_steps: int = 10, headless: bool = True, slow_mo: int = 0):
        """
        初始化浏览器代理

        Args:
            api_key: OpenAI API Key
            max_steps: 最大操作步数
            headless: 是否使用无头模式（False=可以看到浏览器窗口）
            slow_mo: 每个操作延迟毫秒数（便于观察，建议1000-2000）
        """
        self.api_key = api_key
        self.max_steps = max_steps
        self.headless = headless
        self.slow_mo = slow_mo
        self.client = openai.OpenAI(api_key=api_key)

        # 创建截图存储目录
        self.screenshots_dir = Path("task_data/screenshots")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        # 创建报告存储目录
        self.reports_dir = Path("task_data/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # 对话历史管理 - 用于多轮对话和 prompt caching
        self.conversation_history = []
        self.static_system_prompt = None  # 静态 system prompt（可缓存）
        self.current_query = None  # 当前任务查询
        self.history_summary = None  # 历史总结（当对话超过阈值时）
        self.max_history_messages = 20  # 对话历史最大消息数

        # 重复操作检测
        self.recent_actions = []  # 最近的操作记录 [(action, element_id, text), ...]
        self.max_recent_actions = 5  # 保留最近5个操作用于检测重复

        # 任务管理和页面图谱 🆕
        self.task_manager = TaskManager(self.client)
        self.site_graph = SiteGraph()

        # 批量执行引擎和页面缓存 🆕
        self.batch_engine = BatchExecutionEngine()
        self.page_cache: Dict[str, PageSnapshot] = {}  # URL -> 快照

    def _init_conversation(self, query: str):
        """
        初始化对话历史（每个新任务时调用）

        Args:
            query: 用户问题
        """
        self.current_query = query
        self.conversation_history = []
        self.history_summary = None  # 重置历史总结
        self.recent_actions = []  # 重置最近操作记录

        # 重置任务管理和页面图谱 🆕
        self.task_manager = TaskManager(self.client)
        self.site_graph = SiteGraph()

        # 创建静态 system prompt（不包含动态信息，便于 prompt caching）
        self.static_system_prompt = """你是一个专业的网页浏览助手，通过分析标注后的页面截图来操作浏览器。

截图说明：
- 红色边框标注了所有可交互元素
- 每个元素都有编号 [1], [2], [3] 等
- 请直接从截图中识别元素的位置、类型和文本内容
- 只需返回元素编号，系统会自动根据编号定位和操作元素

可用操作：

1. CLICK - 点击某个元素
   - 需要提供: element_id（元素编号）
   - 用途: 点击链接、按钮、菜单等
   - 示例: 点击搜索按钮，选择element_id=2

2. TYPE - 在输入框输入文本
   - 需要提供: element_id（输入框编号）, text（要输入的内容）
   - 用途: 在搜索框、表单等输入信息
   - 注意: 会自动在输入框中输入文本并按回车
   - 示例: 在搜索框输入"中国人口"，选择element_id=1, text="中国人口"

3. SCROLL - 滚动页面或元素
   - 需要提供: scroll_amount（滚动距离，像素）
   - 可选提供: element_id（要滚动的元素编号）
   - 正数向下滚动，负数向上滚动，默认500px
   - 用途:
     * 不指定element_id：滚动整个页面（默认）
     * 指定element_id：滚动特定元素（如文档查看器、iframe、可滚动div）
   - 示例: 滚动页面用scroll_amount=500，滚动元素5用element_id=5, scroll_amount=300

4. BACK - 浏览器后退
   - 不需要额外参数
   - 用途: 返回上一个页面
   - 示例: 点击进入了错误的页面，可以后退重新选择

5. FORWARD - 浏览器前进
   - 不需要额外参数
   - 用途: 前进到下一个页面（在使用后退后）

6. REFRESH - 刷新页面
   - 不需要额外参数
   - 用途: 重新加载当前页面
   - 示例: 页面加载不完整或需要更新数据时使用

7. BATCH_EXECUTE - 批量执行相同操作（⚡ 高效模式）
   - 需要提供: batch_element_ids（元素ID列表）, batch_description（操作描述）
   - 用途: 当需要对多个相似元素执行相同操作时（如批量阅读公告）
   - 使用时机：
     * ✅ 第1次单独执行成功，验证了操作可行
     * ✅ 所有目标元素结构相似（如列表中的多个链接）
     * ✅ 操作流程固定（点击→提取内容）
     * ✅ 没有反爬虫、验证码等障碍
   - 示例:
     ```json
     {
       "action": "BATCH_EXECUTE",
       "batch_element_ids": [12, 19, 26, 33, 40],
       "batch_description": "点击公告链接并提取内容",
       "reasoning": "已验证第1个公告读取成功，剩余4个公告结构相同，使用批量执行提升效率"
     }
     ```
   - ⚡ 优势: 自动使用新标签页模式，列表页保持不变，无需重复提取元素，大幅节省时间
   - ⚠️ 注意: 只有在第1次单独操作成功后才使用，确保流程可行

8. TASK_COMPLETE - 任务完成
   - 需要提供: summary（答案摘要，100-200字）, citations（引用片段列表）
   - 用途: 当找到问题的答案时使用

9. CHECK_DOWNLOADS - 查看已下载文件 (📥 文件系统访问)
   - 不需要额外参数
   - 用途: 查看downloads目录中已下载的文件列表
   - 返回: 文件名、大小、下载时间等信息
   - 使用场景:
     * 确认PDF/文档是否已成功下载
     * 验证文件名和文件大小
     * 检查下载的文件数量
   - 示例: 当点击下载按钮后，使用CHECK_DOWNLOADS确认文件是否已保存到本地

重要提示：
- 请根据截图的视觉信息做决策（截图中的元素已用红框和编号标注）
- 返回元素编号（element_id），系统会自动根据编号定位和操作元素
- 如果需要搜索，直接用TYPE在搜索框输入，不需要再点击搜索按钮
- 每个操作都必须提供reasoning字段说明原因
- 你可以看到之前的操作历史和结果，请根据历史信息做出更好的决策

**浏览器控制操作的使用建议**：
- 🔙 BACK（后退）：当进入错误页面、死胡同、或需要返回上级页面时使用
- 🔜 FORWARD（前进）：在使用后退后，如果需要返回之前访问的页面
- 🔄 REFRESH（刷新）：页面加载不完整、数据需要更新、或出现错误时使用
- 这些操作可以有效避免陷入困境，提高任务成功率

**避免重复操作的策略**：
- ⚠️ 如果某个操作已经执行过但没有产生预期效果，不要重复执行
- ⚠️ 如果收到重复操作警告，必须立即改变策略
- ⚠️ 重复点击同一个元素是无效的，请尝试其他元素或操作
- 建议策略：使用BACK返回上一页、SCROLL查看更多元素、点击其他相关链接、或重新思考任务目标"""

    async def _summarize_conversation_history(self) -> str:
        """
        使用 LLM 总结对话历史

        Returns:
            历史总结文本
        """
        logger.info("开始总结对话历史...")

        # 构建历史文本
        history_text = ""
        for msg in self.conversation_history:
            role = msg['role']
            content = msg['content']

            # 处理不同类型的content
            if isinstance(content, str):
                history_text += f"{role.upper()}: {content}\n\n"
            elif isinstance(content, list):
                # 只提取文本部分
                for item in content:
                    if isinstance(item, dict) and item.get('type') == 'input_text':
                        history_text += f"{role.upper()}: {item.get('text', '')}\n\n"

        # 调用 LLM 总结
        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini-2025-08-07",  
                messages=[
                    {
                        "role": "system",
                        "content": """你是一个专业的对话总结助手。请总结浏览器自动化任务的对话历史。

总结要求：
1. 简明扼要，重点关注：已执行的操作、访问的页面、遇到的问题
2. 使用项目符号列表格式
3. 保留关键信息：URL、操作类型、重要的推理依据
4. 忽略技术细节和元素ID
5. 长度控制在200-300字以内

示例格式：
**已执行操作**：
- 步骤1：在搜索框输入"预制菜定义"
- 步骤2：点击搜索结果中的政府文件链接
- 步骤3：滚动页面查看更多内容

**当前状态**：
- 当前页面：https://www.gov.cn/article/xxx
- 发现的关键信息：..."""
                    },
                    {
                        "role": "user",
                        "content": f"请总结以下对话历史：\n\n{history_text}"
                    }
                ],
                max_completion_tokens=500,  # GPT-5使用max_completion_tokens而不是max_tokens
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"历史总结完成，长度: {len(summary)} 字符")

            return summary

        except Exception as e:
            logger.error(f"总结对话历史失败: {e}")
            # 返回简单的fallback总结
            return f"[对话历史总结失败] 共 {len(self.conversation_history)} 条消息"

    def _check_repeated_action(self, action: str, element_id: Optional[int], text: Optional[str]) -> bool:
        """
        检查是否是重复的操作

        Args:
            action: 操作类型
            element_id: 元素ID
            text: 输入文本

        Returns:
            True 如果是重复操作
        """
        action_tuple = (action, element_id, text)

        # 检查最近的操作中是否有完全相同的
        repeated_count = self.recent_actions.count(action_tuple)

        return repeated_count >= 2  # 如果同样的操作出现2次或以上，认为是重复

    def _record_action(self, action: str, element_id: Optional[int], text: Optional[str]):
        """
        记录操作到最近操作列表

        Args:
            action: 操作类型
            element_id: 元素ID
            text: 输入文本
        """
        action_tuple = (action, element_id, text)
        self.recent_actions.append(action_tuple)

        # 只保留最近的操作
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[-self.max_recent_actions:]

    async def _compress_conversation_history(self):
        """
        压缩对话历史（当消息数超过阈值时）

        流程：
        1. 调用 LLM 总结旧的对话历史
        2. 清理旧历史，只保留最近的几轮
        3. 将总结作为上下文插入
        """
        if len(self.conversation_history) <= self.max_history_messages:
            return  # 未超过阈值，无需压缩

        logger.info(f"对话历史已达到 {len(self.conversation_history)} 条，开始压缩...")

        # 1. 总结旧的对话历史（除了最近5轮）
        old_history = self.conversation_history[:-10]  # 保留最近10条消息不总结
        current_history = self.conversation_history

        # 临时保存当前历史，用于总结
        self.conversation_history = old_history
        summary = await self._summarize_conversation_history()
        self.conversation_history = current_history

        # 2. 更新历史总结
        if self.history_summary:
            # 如果已有总结，追加新的总结
            self.history_summary += f"\n\n**后续操作总结**：\n{summary}"
        else:
            self.history_summary = summary

        # 3. 压缩历史：只保留最近10条消息
        self.conversation_history = self.conversation_history[-10:]

        logger.info(f"压缩完成，保留了最近 {len(self.conversation_history)} 条消息")
        logger.info(f"历史总结长度: {len(self.history_summary)} 字符")

    def get_conversation_stats(self) -> Dict:
        """
        获取对话历史统计信息

        Returns:
            {
                'total_messages': int,
                'user_messages': int,
                'assistant_messages': int,
                'estimated_tokens': int  # 粗略估算
            }
        """
        user_msgs = sum(1 for msg in self.conversation_history if msg['role'] == 'user')
        assistant_msgs = sum(1 for msg in self.conversation_history if msg['role'] == 'assistant')

        # 粗略估算 tokens（假设每个字符约 0.5 token）
        total_chars = 0
        for msg in self.conversation_history:
            if isinstance(msg['content'], str):
                total_chars += len(msg['content'])
            elif isinstance(msg['content'], list):
                for item in msg['content']:
                    if isinstance(item, dict) and item.get('type') == 'input_text':
                        total_chars += len(item.get('text', ''))

        # 加上 static system prompt 的字符数
        total_chars += len(self.static_system_prompt) if self.static_system_prompt else 0

        return {
            'total_messages': len(self.conversation_history),
            'user_messages': user_msgs,
            'assistant_messages': assistant_msgs,
            'estimated_tokens': int(total_chars * 0.5)
        }

    def _export_site_graph(self) -> str:
        """
        导出页面图谱为 Markdown 报告

        Returns:
            Markdown 格式的页面图谱报告
        """
        output = "# 页面导航图谱\n\n"
        output += f"**总访问页面数**: {len(self.site_graph.nodes)}\n\n"

        # 按页面类型分组
        pages_by_type = {
            "entry": [],
            "list": [],
            "detail": [],
            "other": []
        }

        for url, node in self.site_graph.nodes.items():
            pages_by_type[node.page_type].append(node)

        # 输出各类型页面
        type_names = {
            "entry": "入口页面",
            "list": "列表页面",
            "detail": "详情页面",
            "other": "其他页面"
        }

        for page_type, type_name in type_names.items():
            pages = pages_by_type[page_type]
            if pages:
                output += f"## {type_name} ({len(pages)})\n\n"
                for node in pages:
                    output += f"### {node.title or '无标题'}\n\n"
                    output += f"- **URL**: {node.url}\n"
                    output += f"- **访问次数**: {node.visited_count}\n"
                    if node.description:
                        output += f"- **描述**: {node.description}\n"
                    if node.parent_url:
                        parent = self.site_graph.nodes.get(node.parent_url)
                        if parent:
                            output += f"- **来源**: {parent.title or parent.url[:40]}\n"
                    output += "\n"

        # 输出导航历史
        output += "## 导航历史\n\n"
        output += "```\n"
        for i, url in enumerate(self.site_graph.navigation_history, 1):
            node = self.site_graph.nodes.get(url)
            if node:
                output += f"{i}. [{node.page_type}] {node.title or url[:60]}\n"
        output += "```\n"

        return output

    def export_conversation_history(self, output_path: Optional[str] = None) -> str:
        """
        导出对话历史到 JSON 文件（用于调试和分析）

        Args:
            output_path: 输出路径（可选）

        Returns:
            导出的文件路径
        """
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.reports_dir / f"conversation_history_{timestamp}.json"
        else:
            output_path = Path(output_path)

        export_data = {
            'query': self.current_query,
            'static_system_prompt': self.static_system_prompt,
            'conversation_history': self.conversation_history,
            'stats': self.get_conversation_stats()
        }

        output_path.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info(f"对话历史已导出到: {output_path}")

        return str(output_path)

    async def execute_task(self, query: str, target_url: str, task_id: int) -> Dict:
        """
        执行深度搜索任务

        Args:
            query: 用户问题
            target_url: 目标网站URL
            task_id: 任务ID

        Returns:
            {
                'success': bool,
                'summary': str,
                'source_url': str,
                'citations': List[str],
                'steps': List[Dict],
                'report_html_path': str,
                'error': str (if failed)
            }
        """
        logger.info(f"开始执行任务 {task_id}: {query} -> {target_url}")

        async with async_playwright() as p:
            # 启动浏览器（支持有头模式观察操作过程）
            # 添加强化的反检测参数
            browser_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
            ]

            if not self.headless:
                browser_args.append('--start-maximized')

            # 对于高防护网站（如tesla.com），使用真实Chrome浏览器
            use_real_chrome = any(domain in target_url for domain in ['tesla.com', 'saytechnologies.com'])

            if use_real_chrome and not self.headless:
                # 方案：使用系统已安装的真实Chrome（最难被检测）
                logger.info("检测到高防护网站，使用真实Chrome浏览器...")

                # 使用channel参数连接系统Chrome
                try:
                    browser = await p.chromium.launch(
                        channel='chrome',  # 使用系统安装的Chrome
                        headless=False,
                        slow_mo=self.slow_mo,
                        args=['--start-maximized']
                    )
                except Exception as e:
                    logger.warning(f"无法启动系统Chrome: {e}，回退到Chromium")
                    browser = await p.chromium.launch(
                        headless=self.headless,
                        slow_mo=self.slow_mo,
                        args=browser_args
                    )
            else:
                # 其他情况使用标准Chromium
                browser = await p.chromium.launch(
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=browser_args
                )

            # 创建下载目录
            download_path = os.path.join(os.getcwd(), "downloads")
            os.makedirs(download_path, exist_ok=True)
            logger.info(f"📁 下载路径: {download_path}")

            # 创建浏览器上下文（配置下载路径）
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 1024},
                accept_downloads=True  # 允许下载
            )

            # 创建页面并设置反检测
            page = await context.new_page()

            # 设置真实的User-Agent和headers
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
            })

            # 注入强化的反检测脚本
            await page.add_init_script("""
                // 覆盖webdriver属性
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // 覆盖permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // 添加完整的chrome对象
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };

                // 覆盖plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                // 覆盖languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });

                // 覆盖platform
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'MacIntel'
                });

                // 模拟真实的硬件并发数
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });

                // 覆盖deviceMemory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });

                // 添加battery API
                navigator.getBattery = () => {
                    return Promise.resolve({
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: 1
                    });
                };
            """)

            try:
                # 获取browser context（用于批量执行时创建新标签页）
                context = page.context

                # 执行任务
                result = await self._run_browser_loop(
                    page=page,
                    context=context,
                    query=query,
                    target_url=target_url,
                    task_id=task_id
                )

                return result

            except Exception as e:
                logger.error(f"任务 {task_id} 执行失败: {e}")
                import traceback
                traceback.print_exc()
                return {
                    'success': False,
                    'error': str(e)
                }
            finally:
                await browser.close()

    async def _get_interactive_elements(self, page: Page) -> List[dict]:
        """
        提取页面中所有可交互元素

        Returns:
            元素列表，每个元素包含: id, type, text, selector, bbox
        """
        elements_data = await page.evaluate(r"""
            () => {
                const elements = [];
                let id = 1;

                // 优化的交互元素选择器（更全面）
                const interactiveSelectors = [
                    'input:not([type="hidden"])',
                    'textarea',
                    'button',
                    'a',  // 所有a标签（不管是否有href）
                    'select',
                    '[role="button"]',
                    '[role="link"]',
                    '[role="textbox"]',
                    '[onclick]',
                    '[ng-click]',  // Angular点击事件
                    '[data-click]',  // 自定义点击属性
                    '[data-link]',  // 自定义链接属性
                    '[contenteditable="true"]',
                    // 常见的可点击容器
                    'div[onclick]',
                    'span[onclick]',
                    'li[onclick]',
                    'td[onclick]',
                    'tr[onclick]'
                ];

                // 首先获取基本的可交互元素
                let allElements = Array.from(document.querySelectorAll(
                    interactiveSelectors.join(',')
                ));

                // 额外查找：所有cursor为pointer的元素（通常可点击）
                const allDivSpans = document.querySelectorAll('div, span, td, tr, li, p');
                allDivSpans.forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.cursor === 'pointer' && !allElements.includes(el)) {
                        allElements.push(el);
                    }
                });

                allElements.forEach(el => {
                    // 获取元素位置
                    const rect = el.getBoundingClientRect();

                    const style = window.getComputedStyle(el);

                    // 过滤真正不可见的元素
                    if (style.display === 'none') return;
                    if (style.visibility === 'hidden') return;
                    if (parseFloat(style.opacity) < 0.1) return;

                    // 对于链接元素，即使尺寸为0也可能是有效的（表格单元格中的链接）
                    // 只要它有文本内容就保留
                    const isLink = el.tagName === 'A';
                    const hasText = el.innerText && el.innerText.trim().length > 0;

                    // 过滤零尺寸元素（但保留有文本的链接）
                    if (rect.width === 0 || rect.height === 0) {
                        if (!isLink || !hasText) return;
                    }

                    // 放宽视口过滤：允许提取视口下方2000px内的元素（适用于表格、列表等）
                    if (rect.top < -500 || rect.top > window.innerHeight + 2000) return;

                    // 生成稳定的CSS selector（优先级策略）
                    let selector = '';

                    // 优先级1: ID（最稳定）
                    if (el.id) {
                        selector = `#${el.id}`;
                    }
                    // 优先级2: name属性
                    else if (el.name) {
                        selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                    }
                    // 优先级3: data-*属性
                    else if (el.dataset && Object.keys(el.dataset).length > 0) {
                        const key = Object.keys(el.dataset)[0];
                        const value = el.dataset[key];
                        selector = `[data-${key}="${value}"]`;
                    }
                    // 优先级4: class（选择最具体的class）
                    else if (el.className && typeof el.className === 'string') {
                        const classes = el.className.trim().split(/\\s+/)
                            .filter(c => c.length > 0 && c.length < 30)  // 过滤太长的class
                            .slice(0, 2);  // 最多用2个class
                        if (classes.length > 0) {
                            selector = `${el.tagName.toLowerCase()}.${classes.join('.')}`;
                        }
                    }
                    // 优先级5: nth-of-type（最后手段）
                    if (!selector) {
                        const parent = el.parentElement;
                        if (parent) {
                            const siblings = Array.from(parent.children)
                                .filter(e => e.tagName === el.tagName);
                            const index = siblings.indexOf(el) + 1;
                            selector = `${el.tagName.toLowerCase()}:nth-of-type(${index})`;
                        } else {
                            selector = el.tagName.toLowerCase();
                        }
                    }

                    // 优化的文本提取（支持更长的标题）
                    let text = '';

                    // 优先使用innerText（支持换行和可见文本）
                    if (el.innerText && el.innerText.trim()) {
                        let rawText = el.innerText.trim();
                        // 清理多余的空白字符和换行
                        rawText = rawText.replace(/\s+/g, ' ');
                        // 对于链接和标题，保留更多文本（最多100字符）
                        const maxLength = (el.tagName === 'A' || el.tagName === 'H1' || el.tagName === 'H2' || el.tagName === 'H3') ? 100 : 50;
                        text = rawText.substring(0, maxLength);
                    }
                    // textContent作为备选（包含隐藏文本）
                    else if (el.textContent && el.textContent.trim()) {
                        let rawText = el.textContent.trim().replace(/\s+/g, ' ');
                        text = rawText.substring(0, 50);
                    }
                    // 其他属性
                    else if (el.placeholder) {
                        text = `[placeholder: ${el.placeholder.substring(0, 50)}]`;
                    } else if (el.getAttribute('aria-label')) {
                        text = `[aria: ${el.getAttribute('aria-label').substring(0, 50)}]`;
                    } else if (el.value) {
                        text = `[value: ${el.value.substring(0, 30)}]`;
                    } else if (el.alt) {
                        text = `[alt: ${el.alt.substring(0, 50)}]`;
                    } else if (el.title) {
                        text = `[title: ${el.title.substring(0, 50)}]`;
                    }

                    // 跳过空文本元素（但保留输入框）
                    if (!text && el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && el.tagName !== 'SELECT') {
                        return;
                    }

                    // 检测是否为可滚动容器
                    let isScrollable = false;
                    const overflowY = style.overflowY;
                    const overflowX = style.overflowX;

                    if ((overflowY === 'scroll' || overflowY === 'auto' ||
                         overflowX === 'scroll' || overflowX === 'auto') &&
                        (el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth)) {
                        isScrollable = true;
                    }

                    // 为每个元素添加唯一的data属性（确保一一对应）
                    const uniqueId = `ba-${id}`;
                    el.setAttribute('data-browser-agent-id', uniqueId);

                    // 对于零尺寸的链接，尝试使用父元素的尺寸
                    let finalRect = rect;
                    if ((rect.width === 0 || rect.height === 0) && isLink && el.parentElement) {
                        finalRect = el.parentElement.getBoundingClientRect();
                    }

                    elements.push({
                        id: id++,
                        type: el.tagName.toLowerCase(),
                        role: el.getAttribute('role') || '',
                        text: text,
                        selector: selector,
                        uniqueSelector: `[data-browser-agent-id="${uniqueId}"]`,  // 唯一selector
                        isScrollable: isScrollable,  // 标记是否可滚动
                        bbox: {
                            x: Math.round(finalRect.x),
                            y: Math.round(finalRect.y),
                            width: Math.round(finalRect.width),
                            height: Math.round(finalRect.height)
                        }
                    });
                });

                // 额外检测iframe和可滚动容器（即使它们不是可交互元素）
                const scrollableContainers = document.querySelectorAll('iframe, [style*="overflow"]');
                scrollableContainers.forEach(el => {
                    // 如果已经被添加，跳过
                    if (el.hasAttribute('data-browser-agent-id')) return;

                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) return;
                    if (rect.top < -500 || rect.top > window.innerHeight + 2000) return;

                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return;

                    // 检查是否真的可滚动
                    const overflowY = style.overflowY;
                    const overflowX = style.overflowX;
                    const isScrollable = (overflowY === 'scroll' || overflowY === 'auto' ||
                                         overflowX === 'scroll' || overflowX === 'auto') &&
                                        (el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth);

                    const isIframe = el.tagName.toLowerCase() === 'iframe';

                    if (!isScrollable && !isIframe) return;

                    const uniqueId = `ba-${id}`;
                    el.setAttribute('data-browser-agent-id', uniqueId);

                    let text = '[可滚动容器]';
                    if (isIframe) {
                        text = '[iframe]';
                        const title = el.getAttribute('title');
                        if (title) text = `[iframe: ${title.substring(0, 30)}]`;
                    }

                    elements.push({
                        id: id++,
                        type: el.tagName.toLowerCase(),
                        role: '',
                        text: text,
                        selector: el.id ? `#${el.id}` : el.tagName.toLowerCase(),
                        uniqueSelector: `[data-browser-agent-id="${uniqueId}"]`,
                        isScrollable: true,
                        bbox: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        }
                    });
                });

                return elements;
            }
        """)

        logger.info(f"提取到 {len(elements_data)} 个可交互元素")
        return elements_data

    async def _get_or_cache_elements(self, page: Page, force_refresh: bool = False) -> List[dict]:
        """
        获取页面元素（带缓存）

        Args:
            page: 当前页面
            force_refresh: 强制刷新，不使用缓存

        Returns:
            元素列表
        """
        import hashlib

        current_url = page.url

        # 计算页面HTML的哈希（用于检测变化）
        html_hash = await page.evaluate("() => document.body.innerHTML.substring(0, 2000)")
        html_hash = hashlib.md5(html_hash.encode()).hexdigest()

        # 检查缓存
        if not force_refresh and current_url in self.page_cache:
            snapshot = self.page_cache[current_url]
            if snapshot.is_valid(current_url, html_hash):
                logger.info(f"✅ 使用缓存的页面元素 ({len(snapshot.elements)}个)")
                return snapshot.elements
            else:
                logger.info("⚠️  页面已变化，重新提取元素")

        # 提取元素
        logger.info("🔍 提取页面元素...")
        elements = await self._get_interactive_elements(page)

        # 缓存
        self.page_cache[current_url] = PageSnapshot(
            url=current_url,
            timestamp=datetime.now(),
            elements=elements,
            html_hash=html_hash
        )

        logger.info(f"💾 已缓存页面元素 ({len(elements)}个)")
        return elements

    def _setup_download_listener(self, page):
        """
        为指定的page对象设置下载事件监听器

        Args:
            page: Playwright Page对象
        """
        async def handle_download(download):
            """处理下载事件"""
            try:
                # 获取建议的文件名
                suggested_filename = download.suggested_filename
                # 保存到downloads目录
                file_path = os.path.join(self.download_path, suggested_filename)

                # 检查文件是否已存在（忽略大小写，避免重复下载）
                existing_files = [f.lower() for f in self.downloaded_files]
                if file_path.lower() in existing_files:
                    logger.info(f"⏭️  文件已存在，跳过下载: {suggested_filename}")
                    return

                await download.save_as(file_path)
                self.downloaded_files.append(file_path)
                logger.info(f"✅ 文件已下载: {file_path}")
            except Exception as e:
                logger.error(f"❌ 下载失败: {e}")

        # 监听下载事件
        page.on("download", handle_download)
        logger.info(f"📥 已为页面设置下载监听器: {page.url[:60]}...")

    def _get_downloads_info(self) -> str:
        """
        获取下载目录中的文件信息

        Returns:
            str: 格式化的文件列表信息
        """
        download_path = os.path.join(os.getcwd(), "downloads")

        if not os.path.exists(download_path):
            return "📥 **下载目录**: 空（尚未下载任何文件）"

        files = []
        for filename in os.listdir(download_path):
            file_path = os.path.join(download_path, filename)
            if os.path.isfile(file_path):
                # 获取文件信息
                size = os.path.getsize(file_path)
                size_kb = size / 1024
                mtime = os.path.getmtime(file_path)
                from datetime import datetime
                mod_time = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')

                files.append({
                    'name': filename,
                    'size_kb': size_kb,
                    'modified': mod_time
                })

        if not files:
            return "📥 **下载目录**: 空（尚未下载任何文件）"

        # 按修改时间排序（最新的在前）
        files.sort(key=lambda x: x['modified'], reverse=True)

        # 格式化输出
        info_lines = [f"📥 **下载目录**: {len(files)} 个文件"]
        for i, f in enumerate(files, 1):
            info_lines.append(f"  {i}. {f['name']} ({f['size_kb']:.1f}KB, {f['modified']})")

        return "\n".join(info_lines)

    def _annotate_screenshot(self, screenshot_bytes: bytes, elements: List[dict]) -> bytes:
        """
        在截图上绘制元素标注（红框+编号）

        Args:
            screenshot_bytes: 原始截图字节
            elements: 元素列表

        Returns:
            标注后的截图字节
        """
        if not Image or not ImageDraw or not ImageFont:
            logger.warning("PIL未安装，返回原始截图")
            return screenshot_bytes

        try:
            # 加载截图
            image = Image.open(io.BytesIO(screenshot_bytes))
            draw = ImageDraw.Draw(image)

            # 尝试加载字体
            font = None
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",  # macOS
                "/System/Library/Fonts/Supplemental/Arial.ttf",  # macOS
                "C:\\Windows\\Fonts\\arial.ttf",  # Windows
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            ]
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, 16)
                    break
                except:
                    continue

            if not font:
                font = ImageFont.load_default()

            # 获取截图尺寸
            img_width, img_height = image.size

            # 只标注在截图范围内可见的元素（避免标注视口外的元素）
            visible_elements = []
            for elem in elements:
                bbox = elem['bbox']
                x, y, w, h = bbox['x'], bbox['y'], bbox['width'], bbox['height']

                # 检查元素是否在截图范围内（至少部分可见）
                if x < img_width and y < img_height and (x + w) > 0 and (y + h) > 0:
                    visible_elements.append(elem)

            logger.info(f"截图尺寸: {img_width}x{img_height}, 可见元素: {len(visible_elements)}/{len(elements)}")

            # 绘制每个可见元素的标注（限制最多100个避免太乱）
            for elem in visible_elements[:100]:
                bbox = elem['bbox']
                x, y, w, h = bbox['x'], bbox['y'], bbox['width'], bbox['height']

                # 绘制红色边框（2px）
                draw.rectangle(
                    [(x, y), (x + w, y + h)],
                    outline='#FF0000',
                    width=2
                )

                # 绘制编号标签
                label = f"[{elem['id']}]"

                # 计算标签尺寸
                try:
                    bbox_text = draw.textbbox((0, 0), label, font=font)
                    label_width = bbox_text[2] - bbox_text[0] + 8
                    label_height = bbox_text[3] - bbox_text[1] + 4
                except:
                    label_width = len(label) * 10
                    label_height = 18

                # 标签位置（避免超出顶部）
                label_y = max(0, y - label_height - 2)

                # 标签背景（红色）
                draw.rectangle(
                    [(x, label_y), (x + label_width, label_y + label_height)],
                    fill='#FF0000'
                )

                # 标签文字（白色）
                draw.text(
                    (x + 4, label_y + 2),
                    label,
                    fill='white',
                    font=font
                )

            # 转换回bytes
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()

        except Exception as e:
            logger.error(f"截图标注失败: {e}")
            return screenshot_bytes

    async def _run_browser_loop(self, page: Page, context, query: str, target_url: str, task_id: int) -> Dict:
        """
        执行浏览器操作循环

        Args:
            page: 当前页面
            context: Browser context（用于创建新标签页）
            query: 用户查询
            target_url: 目标URL
            task_id: 任务ID
        """
        steps = []
        step_count = 0

        # 初始化对话历史
        self._init_conversation(query)
        logger.info(f"已初始化对话历史，任务: {query}")

        # 🆕 任务拆解
        await self.task_manager.decompose_task(query)
        logger.info(f"任务已拆解为 {len(self.task_manager.subtasks)} 个子任务")

        # 📥 初始化下载相关变量
        self.download_path = os.path.join(os.getcwd(), "downloads")
        self.downloaded_files = []  # 记录已下载的文件（任务级别）

        # 📥 设置下载事件监听（为初始页面）
        self._setup_download_listener(page)
        logger.info(f"📥 下载监听已启动，文件将保存到: {self.download_path}")

        # 访问目标URL
        logger.info(f"访问目标URL: {target_url}")
        await page.goto(target_url, wait_until='networkidle', timeout=30000)
        current_url = page.url

        # 🆕 添加初始页面到图谱
        self.site_graph.add_or_update_page(
            url=current_url,
            page_type="entry",
            title="起始页面",
            description="任务开始的页面"
        )

        # 主循环（视觉标注方案）
        elements = []  # 当前页面的可交互元素列表

        while step_count < self.max_steps:
            step_count += 1
            logger.info(f"执行第 {step_count} 步...")

            # ⚠️ 重要：先更新 current_url，确保截图和 URL 一致
            current_url = page.url
            logger.info(f"📍 当前页面: {current_url}")

            # 1. 提取可交互元素
            elements = await self._get_interactive_elements(page)

            # 2. 截图（原始）
            screenshot_bytes = await page.screenshot(full_page=False)

            # 3. 在截图上标注元素
            annotated_screenshot_bytes = self._annotate_screenshot(screenshot_bytes, elements)

            # 4. 保存标注后的截图
            screenshot_path = self.screenshots_dir / f"task_{task_id}_step_{step_count}_annotated.png"
            screenshot_path.write_bytes(annotated_screenshot_bytes)
            logger.info(f"📸 截图已保存: {screenshot_path.name} (页面: {current_url[:60]}...)")

            # 5. 转换为base64
            screenshot_base64 = base64.b64encode(annotated_screenshot_bytes).decode()

            # 6. 调用视觉模型分析（发送标注后的截图和元素列表）
            decision = await self._analyze_page(
                screenshot_base64=screenshot_base64,
                elements=elements,
                query=query,
                current_url=current_url,  # ✅ 现在这个 URL 和截图一致
                step_count=step_count,
                task_id=task_id
            )

            # 记录步骤
            step_record = {
                'step': step_count,
                'screenshot': str(screenshot_path),
                'url': current_url,
                'action': decision.get('action'),
                'reasoning': decision.get('reasoning', ''),
                'element_id': decision.get('element_id')
            }
            steps.append(step_record)

            logger.info(f"决策: {decision.get('action')} - {decision.get('reasoning', '')[:100]}")

            # 7. 检查是否完成
            if decision.get('action') == 'TASK_COMPLETE':
                logger.info("任务完成！")

                # 获取最终页面HTML
                html_content = await page.content()

                # 生成高亮HTML
                report_html_path = await self._generate_highlighted_html(
                    html_content=html_content,
                    citations=decision.get('citations', []),
                    task_id=task_id
                )

                # 自动导出对话历史
                history_path = self.export_conversation_history()
                logger.info(f"对话历史已自动导出: {history_path}")

                # 🆕 导出任务报告
                task_report = self.task_manager.export_results()
                task_report_path = self.reports_dir / f"task_{task_id}_subtasks.md"
                task_report_path.write_text(task_report, encoding='utf-8')
                logger.info(f"📋 任务报告已导出: {task_report_path}")

                # 🆕 导出页面图谱
                graph_report = self._export_site_graph()
                graph_report_path = self.reports_dir / f"task_{task_id}_site_graph.md"
                graph_report_path.write_text(graph_report, encoding='utf-8')
                logger.info(f"🗺️  页面图谱已导出: {graph_report_path}")

                # 📥 汇总下载文件
                logger.info(f"📥 共下载了 {len(self.downloaded_files)} 个文件:")
                for file_path in self.downloaded_files:
                    logger.info(f"   - {os.path.basename(file_path)}")

                return {
                    'success': True,
                    'summary': decision.get('summary', ''),
                    'source_url': current_url,
                    'citations': decision.get('citations', []),
                    'steps': steps,
                    'report_html_path': report_html_path,
                    'conversation_history_path': history_path,  # 返回对话历史路径
                    'task_report_path': str(task_report_path),  # 🆕 任务报告路径
                    'graph_report_path': str(graph_report_path),  # 🆕 页面图谱路径
                    'downloaded_files': self.downloaded_files,  # 📥 下载的文件列表
                    'download_count': len(self.downloaded_files)  # 📥 下载文件数量
                }

            # 8. 执行操作（传递元素列表）
            try:
                # 处理批量执行
                if decision.get('action') == 'BATCH_EXECUTE':
                    await self._handle_batch_execute(
                        page=page,
                        context=context,
                        decision=decision,
                        query=query
                    )
                    # 批量执行完成后继续循环，让LLM做总结
                    continue

                # 执行操作并获取可能更新的 page 对象（新标签页）
                page = await self._execute_action(page, decision, elements)
                new_url = page.url

                # 🆕 更新页面图谱
                if new_url != current_url:
                    # 推测页面类型
                    page_type = "other"
                    if "list" in new_url or "search" in new_url or "disclosure" in new_url:
                        page_type = "list"
                    elif "detail" in new_url or "article" in new_url or "notice" in new_url:
                        page_type = "detail"

                    page_title = await page.title()
                    self.site_graph.add_or_update_page(
                        url=new_url,
                        page_type=page_type,
                        title=page_title,
                        description=f"从 {self.site_graph.current_url[:40] if self.site_graph.current_url else 'unknown'} 导航而来"
                    )
                    self.site_graph.mark_navigation(current_url, new_url, decision.get('action'))

                # 记录操作结果到对话历史
                if new_url != current_url:
                    result_message = f"操作已执行，页面已跳转到: {new_url}"
                    logger.info(f"🔄 页面跳转: {current_url[:50]}... -> {new_url[:50]}...")
                else:
                    result_message = f"操作已执行完成"
                    logger.info(f"✅ 操作完成（页面未跳转）")

                self.conversation_history.append({
                    "role": "user",
                    "content": result_message
                })

                # ⚠️ 注意：不在这里更新 current_url，而是在下一次循环开始时统一更新
                # 这样确保截图时的 URL 总是最新的
                logger.info(f"操作结果已记录到对话历史")

                # 🆕 检查当前子任务是否完成（让 LLM 判断）
                await self._check_subtask_completion(page)

            except Exception as e:
                logger.error(f"执行操作失败: {e}")
                step_record['error'] = str(e)

                # 记录错误到对话历史
                self.conversation_history.append({
                    "role": "user",
                    "content": f"操作执行失败: {str(e)}"
                })
                # 继续下一步

        # 达到最大步数
        logger.warning(f"达到最大步数 {self.max_steps}，任务未完成")

        # 任务失败时也自动导出对话历史
        history_path = self.export_conversation_history()
        logger.info(f"对话历史已自动导出: {history_path}")

        return {
            'success': False,
            'error': f'达到最大步数 {self.max_steps}，未找到答案',
            'steps': steps,
            'conversation_history_path': history_path
        }

    async def _analyze_page(
        self,
        screenshot_base64: str,
        elements: List[dict],
        query: str,
        current_url: str,
        step_count: int,
        task_id: int
    ) -> Dict:
        """
        调用多模态模型分析当前页面（视觉标注方案，支持对话历史）

        Args:
            screenshot_base64: 标注后的截图（base64）
            elements: 可交互元素列表
            query: 用户问题
            current_url: 当前URL
            step_count: 当前步数
            task_id: 任务ID（用于保存调试信息）

        Returns:
            {
                'action': 'CLICK' | 'TYPE' | 'SCROLL' | 'TASK_COMPLETE',
                'reasoning': str,
                'element_id': int (for CLICK/TYPE),
                'text': str (for TYPE),
                'scroll_amount': int (for SCROLL),
                'summary': str (for TASK_COMPLETE),
                'citations': List[str] (for TASK_COMPLETE)
            }
        """

        # 检测最近的重复操作
        repeated_actions_warning = ""
        if len(self.recent_actions) >= 2:
            # 统计最近操作中的重复
            action_counts = {}
            for action, elem_id, _ in self.recent_actions:  # _ 表示忽略text
                key = (action, elem_id)
                action_counts[key] = action_counts.get(key, 0) + 1

            # 找出重复的操作
            repeated = [(action, elem_id, count) for (action, elem_id), count in action_counts.items() if count >= 2]
            if repeated:
                warnings = []
                for action, elem_id, count in repeated:
                    warnings.append(f"  - {action} 元素{elem_id}（已重复{count}次）")
                repeated_actions_warning = f"\n\n⚠️ **警告：检测到重复操作**：\n" + "\n".join(warnings) + "\n请尝试不同的策略，避免无效的重复操作！"

        # 🆕 获取任务进度和导航上下文
        task_progress = self.task_manager.get_progress_summary()
        navigation_context = self.site_graph.get_navigation_context()

        # 构建当前步骤的用户消息（包含动态信息）
        # 优化：不再发送元素列表文本，只发送截图（已标注元素编号）
        # 这样可以大幅减少 token 消耗（约 80-90%），充分利用 GPT-5 的视觉能力

        # 获取下载目录文件信息
        downloads_info = self._get_downloads_info()

        # 获取下载文件数量，用于决定是否显示提示
        download_count = len(self.downloaded_files) if hasattr(self, 'downloaded_files') else 0
        download_hint = ""
        if download_count > 0:
            download_hint = f"\n\n💡 **重要提示**: 已有 {download_count} 个文件下载成功！如果任务目标是下载文件，请检查上方的【下载目录】信息，确认文件是否符合要求。"

        # 只在首轮（step_count == 1）发送总体任务信息
        if step_count == 1:
            current_step_info = f"""**总体任务**: {query}

{task_progress}

{navigation_context}

{downloads_info}

**当前页面URL**: {current_url}
**当前步数**: {step_count}/{self.max_steps}
**可交互元素数量**: {len(elements)} 个{repeated_actions_warning}{download_hint}

请分析这个标注后的页面截图（红色框和数字表示可交互元素的编号），决定下一步操作。注意：**必须完成当前子任务后再进行下一个**！"""
        else:
            # 后续步骤只发送动态变化的信息
            current_step_info = f"""{task_progress}

{navigation_context}

{downloads_info}

**当前页面URL**: {current_url}
**当前步数**: {step_count}/{self.max_steps}
**可交互元素数量**: {len(elements)} 个{repeated_actions_warning}{download_hint}

请分析这个标注后的页面截图（红色框和数字表示可交互元素的编号），决定下一步操作。注意：**必须完成当前子任务后再进行下一个**！"""

        # 检查并压缩对话历史（如果超过阈值）
        await self._compress_conversation_history()

        # 构建完整的消息列表
        messages = []

        # 1. 添加静态 system prompt（第一次调用时会被缓存）
        messages.append({
            "role": "system",
            "content": self.static_system_prompt
        })

        # 2. 如果有历史总结，添加到消息列表中
        if self.history_summary:
            messages.append({
                "role": "user",
                "content": f"**之前的操作历史总结**：\n{self.history_summary}"
            })
            messages.append({
                "role": "assistant",
                "content": "我已了解之前的操作历史，会基于这些信息继续执行任务。"
            })

        # 3. 添加历史对话（压缩后的最近对话）
        messages.extend(self.conversation_history)

        # 4. 添加当前步骤的消息
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": current_step_info
                },
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}"
                }
            ]
        })

        # 💾 保存发送给 LLM 的消息到本地（用于调试和 token 分析）
        try:
            debug_dir = Path("debug_messages")
            debug_dir.mkdir(exist_ok=True)

            # 保存消息内容（不包含base64图片，太大）
            messages_for_debug = []
            for msg in messages:
                if isinstance(msg.get('content'), list):
                    # 处理包含图片的消息
                    debug_content = []
                    for item in msg['content']:
                        if item.get('type') == 'input_image':
                            debug_content.append({
                                'type': 'input_image',
                                'image_url': '[BASE64_IMAGE_OMITTED]',
                                'image_size_estimate': f'~{len(item.get("image_url", ""))} chars'
                            })
                        else:
                            debug_content.append(item)
                    messages_for_debug.append({
                        'role': msg['role'],
                        'content': debug_content
                    })
                else:
                    messages_for_debug.append(msg)

            debug_file = debug_dir / f"task_{task_id}_step_{step_count}_messages.json"
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'task_id': task_id,
                    'step_count': step_count,
                    'current_url': current_url,
                    'messages': messages_for_debug,
                    'elements_count': len(elements)
                }, f, ensure_ascii=False, indent=2)

            logger.info(f"💾 已保存消息到: {debug_file}")
        except Exception as e:
            logger.warning(f"保存调试消息失败: {e}")

        try:
            response = self.client.responses.parse(
                model="gpt-5-mini-2025-08-07",
                input=messages,
                text_format=BrowserDecision,
                max_output_tokens=50000,
            )

            # 直接获取解析后的结构化对象
            decision_obj: BrowserDecision = response.output_parsed
            decision_dict = decision_obj.model_dump()

            # 清理 text 字段中可能的 JSON 格式残留符号
            # 注意：即使使用 OpenAI Structured Outputs，模型仍可能在字符串字段中
            # "泄漏"JSON 结构符号（如 "300866}"），因为这在 JSON 语法上是合法的
            if decision_dict.get('text'):
                import re
                original_text = decision_dict['text']
                # 移除末尾的 JSON 格式符号（如 }, ]{, }{ 等组合）
                text = original_text.strip()
                # 使用正则移除末尾的所有 JSON 格式字符（包括 { [ } ] , " ' `）
                text = re.sub(r'[}\]\[\{,\"\'`]+$', '', text).strip()

                if text != original_text:
                    logger.warning(f"🧹 清理 text 字段: '{original_text}' -> '{text}'")

                decision_dict['text'] = text

            # 保存当前用户消息到历史（不包含图片，节省空间）
            self.conversation_history.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": current_step_info + "\n[截图已省略]"
                    }
                ]
            })

            # 保存模型响应到历史
            assistant_message = f"""决策: {decision_dict['action']}
推理: {decision_dict['reasoning']}"""

            if decision_dict.get('element_id'):
                assistant_message += f"\n元素ID: {decision_dict['element_id']}"
            if decision_dict.get('text'):
                assistant_message += f"\n输入文本: {decision_dict['text']}"
            if decision_dict.get('scroll_amount'):
                assistant_message += f"\n滚动距离: {decision_dict['scroll_amount']}px"

            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })

            # 记录操作到最近操作列表（用于检测重复）
            if decision_dict['action'] != 'TASK_COMPLETE':
                self._record_action(
                    decision_dict['action'],
                    decision_dict.get('element_id'),
                    decision_dict.get('text')
                )

            logger.info(f"对话历史长度: {len(self.conversation_history)} 条消息")

            return decision_dict

        except Exception as e:
            logger.error(f"视觉模型调用失败: {e}")
            import traceback
            traceback.print_exc()

            # 返回默认决策
            return {
                'action': 'TASK_COMPLETE',
                'reasoning': f'模型调用失败: {e}',
                'summary': '抱歉，无法完成任务',
                'citations': []
            }

    async def _check_subtask_completion(self, page: Page):
        """
        检查当前子任务是否完成（使用 LLM 判断）

        让 LLM 基于当前页面内容判断子任务是否达成目标
        """
        current_subtask = self.task_manager.get_current_subtask()
        if not current_subtask or current_subtask.status == "completed":
            return

        # 标记为进行中（如果还没标记）
        if current_subtask.status == "pending":
            self.task_manager.mark_current_subtask_in_progress()

        # 获取页面文本摘要
        try:
            page_text = await page.evaluate("""
                () => {
                    // 提取页面主要文本（前2000字符）
                    return document.body.innerText.substring(0, 2000);
                }
            """)
        except:
            page_text = ""

        # 使用 LLM 判断子任务是否完成（基于 success_criteria）
        try:
            # 构建验证条件文本
            criteria_text = "\n".join([f"- {criterion}" for criterion in current_subtask.success_criteria])

            response = self.client.responses.parse(
                model="gpt-5-mini-2025-08-07",
                input=[
                    {
                        "role": "system",
                        "content": """你是一个任务状态验证专家。根据目标状态的验证条件，判断当前是否已达成目标。

**核心原则**：
- 验证**状态是否基本达成**，而不是要求100%完美
- 根据提供的 success_criteria（完成条件）评估，但**允许弹性**
- 如果**主要目标明显已达成**（如找到了列表页面、下载了文件），就可以判断为完成
- 不要因为次要细节未满足就卡住流程

**判断依据**：
- 当前页面的 URL、标题、可见内容
- 是否符合目标状态的主要描述
- 关键验证条件是否满足（允许部分满足）

**示例1**：
目标状态："已找到公告列表页面"
验证条件：["页面URL包含'公告'关键词", "页面中有多条公告"]
判断：如果当前页面显示了明显的公告列表（即使URL不完全匹配），就判断为**已完成**

**示例2**：
目标状态："已下载至少5条公告PDF到本地"
验证条件：["本地存在至少5个PDF文件"]
判断：即使只下载了3个PDF，如果下载过程正在进行中，也可以继续，不要死板地卡在"必须5个"

**重要**：保持**实用主义**，优先让任务继续推进，而不是追求完美验证。"""
                    },
                    {
                        "role": "user",
                        "content": f"""**目标状态**: {current_subtask.description}

**验证条件**：
{criteria_text}

**当前页面信息**：
- URL: {page.url}
- 标题: {await page.title()}
- 内容摘要: {page_text[:800]}...

**本地下载文件信息**：
{self._get_downloads_info()}

**重要提示**：
- 如果任务涉及文件下载，请检查"本地下载文件信息"部分
- 如果下载目录中已有符合要求的文件（文件名、大小、时间合理），即可认为下载成功
- 不需要验证文件"可打开"，文件存在且大小>0即可

请判断目标状态是否已达成（所有关键验证条件是否满足）。"""
                    }
                ],
                text_format=SubtaskCompletionCheck,
                max_output_tokens=2000,
            )

            # 获取结构化输出
            check: SubtaskCompletionCheck = response.output_parsed

            if check.completed:
                logger.info(f"✅ 子任务 #{current_subtask.id} 已完成: {current_subtask.description}")
                logger.info(f"   原因: {check.reason}")

                self.task_manager.mark_current_subtask_complete(
                    result=check.reason
                )
            else:
                logger.info(f"⏳ 子任务 #{current_subtask.id} 尚未完成: {check.reason}")

        except Exception as e:
            logger.warning(f"子任务完成检查失败: {e}，继续执行")

    async def _execute_action(
        self,
        page: Page,
        decision: Dict,
        elements: List[dict],
        max_retries: int = 3
    ) -> Page:
        """
        执行浏览器操作（视觉标注方案 - 基于element_id）

        Args:
            page: Playwright页面对象
            decision: 决策字典（包含action和element_id）
            elements: 可交互元素列表
            max_retries: 最大重试次数

        Returns:
            Page: 当前活动的页面对象（可能是新打开的标签页）
        """
        action = decision.get('action')

        if action == 'CLICK':
            element_id = decision.get('element_id')
            if not element_id:
                logger.warning("CLICK操作缺少element_id")
                return

            # 找到对应的元素
            elem = next((e for e in elements if e['id'] == element_id), None)
            if not elem:
                logger.error(f"未找到元素ID: {element_id}")
                return

            # 使用唯一selector（100%一一对应）
            unique_selector = elem.get('uniqueSelector') or elem['selector']
            fallback_selector = elem['selector']

            logger.info(f"点击元素 [{elem['id']}]: {elem['text']}")
            logger.info(f"  唯一定位符: {unique_selector}")

            # 获取当前浏览器上下文（用于检测新标签页）
            context = page.context
            initial_pages = context.pages

            # 重试机制
            for attempt in range(max_retries):
                try:
                    # 优先使用唯一selector
                    locator = page.locator(unique_selector)

                    # 验证元素存在且唯一
                    count = await locator.count()
                    if count == 0:
                        logger.warning(f"唯一selector未找到元素，尝试fallback")
                        locator = page.locator(fallback_selector).first
                    elif count > 1:
                        logger.warning(f"⚠️  找到{count}个匹配元素，使用第一个")
                        locator = locator.first
                    else:
                        logger.info(f"✓ 唯一定位成功")

                    # 等待元素可见
                    await locator.wait_for(state='visible', timeout=5000)

                    # 滚动到视图
                    await locator.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    # 执行点击（可能打开新标签页）
                    await locator.click()
                    logger.info(f"✅ 点击成功")

                    # 等待页面响应
                    try:
                        await page.wait_for_load_state('networkidle', timeout=10000)
                    except:
                        # 可能没有网络请求，等待DOM变化
                        await asyncio.sleep(1)

                    # 检查是否打开了新标签页
                    await asyncio.sleep(0.5)  # 等待新标签页完全打开
                    current_pages = context.pages

                    if len(current_pages) > len(initial_pages):
                        # 有新标签页打开，切换到最新的标签页
                        new_page = current_pages[-1]
                        logger.info(f"🆕 检测到新标签页，切换到: {new_page.url}")

                        # 等待新页面加载
                        try:
                            await new_page.wait_for_load_state('networkidle', timeout=10000)
                        except:
                            await asyncio.sleep(1)

                        # 📥 为新标签页设置下载监听器
                        self._setup_download_listener(new_page)

                        return new_page

                    return page

                except Exception as e:
                    logger.warning(f"点击尝试 {attempt + 1}/{max_retries} 失败: {str(e)[:100]}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"❌ 点击最终失败: {e}")

            return page

        elif action == 'TYPE':
            element_id = decision.get('element_id')
            text = decision.get('text', '')

            if not element_id:
                logger.warning("TYPE操作缺少element_id")
                return

            # 找到对应的元素
            elem = next((e for e in elements if e['id'] == element_id), None)
            if not elem:
                logger.error(f"未找到元素ID: {element_id}")
                return

            # 使用唯一selector（100%一一对应）
            unique_selector = elem.get('uniqueSelector') or elem['selector']
            fallback_selector = elem['selector']

            logger.info(f"在元素 [{elem['id']}] 输入: {text}")
            logger.info(f"  唯一定位符: {unique_selector}")

            # 重试机制
            for attempt in range(max_retries):
                try:
                    # 优先使用唯一selector
                    locator = page.locator(unique_selector)

                    # 验证元素存在且唯一
                    count = await locator.count()
                    if count == 0:
                        logger.warning(f"唯一selector未找到元素，尝试fallback")
                        locator = page.locator(fallback_selector).first
                    elif count > 1:
                        logger.warning(f"⚠️  找到{count}个匹配元素，使用第一个")
                        locator = locator.first
                    else:
                        logger.info(f"✓ 唯一定位成功")

                    # 等待元素可见
                    await locator.wait_for(state='visible', timeout=5000)

                    # 滚动到视图
                    await locator.scroll_into_view_if_needed()
                    await asyncio.sleep(0.5)

                    # 点击激活输入框
                    await locator.click()
                    await asyncio.sleep(0.2)

                    # 清空并输入
                    await locator.fill(text)
                    logger.info(f"✅ 输入成功")

                    # 按回车（通常用于搜索）
                    await locator.press('Enter')

                    # 等待页面响应
                    try:
                        await page.wait_for_load_state('networkidle', timeout=10000)
                    except:
                        await asyncio.sleep(1)

                    return page

                except Exception as e:
                    logger.warning(f"输入尝试 {attempt + 1}/{max_retries} 失败: {str(e)[:100]}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"❌ 输入失败: {e}")

            return page

        elif action == 'SCROLL':
            scroll_amount = decision.get('scroll_amount', 500)
            element_id = decision.get('element_id')  # 可选：指定要滚动的元素

            if element_id:
                # 滚动特定元素（如 iframe、可滚动 div）
                elem = next((e for e in elements if e['id'] == element_id), None)
                if not elem:
                    logger.error(f"未找到要滚动的元素ID: {element_id}")
                    return page

                logger.info(f"滚动元素 [{elem['id']}]: {elem['text']} ({scroll_amount}px)")

                try:
                    unique_selector = elem.get('uniqueSelector') or elem['selector']
                    # 滚动特定元素
                    await page.locator(unique_selector).evaluate(
                        f"element => element.scrollBy(0, {scroll_amount})"
                    )
                    logger.info(f"✅ 元素滚动成功")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"元素滚动失败: {e}")

            else:
                # 滚动整个页面（默认行为）
                logger.info(f"滚动页面: {scroll_amount}px")

                try:
                    # 使用 window.scrollBy 明确滚动页面，避免歧义
                    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                    logger.info(f"✅ 页面滚动成功")
                    await asyncio.sleep(1)  # 等待内容加载
                except Exception as e:
                    logger.error(f"页面滚动失败: {e}")

            return page

        elif action == 'BACK':
            logger.info("🔙 浏览器后退")

            try:
                # 检查当前页面是否有历史记录
                # 如果是新打开的标签页，可能没有历史记录
                context = page.context
                all_pages = context.pages

                # 尝试后退
                try:
                    await page.go_back(wait_until='networkidle', timeout=10000)
                    logger.info(f"✅ 已返回上一页: {page.url}")
                    return page
                except Exception as e:
                    # 后退失败，可能是新标签页或已经在第一页
                    logger.warning(f"⚠️  后退失败: {e}")

                    # 如果有多个标签页，可能当前是新打开的标签页
                    if len(all_pages) > 1:
                        logger.info("🔄 当前页面可能是新标签页，尝试关闭并返回上一个标签页")

                        # 保存当前页面索引
                        current_index = all_pages.index(page)

                        # 关闭当前标签页
                        await page.close()
                        logger.info("✅ 已关闭当前标签页")

                        # 返回到上一个标签页（如果当前是最后一个，返回倒数第二个）
                        if current_index > 0:
                            previous_page = all_pages[current_index - 1]
                        else:
                            # 当前是第一个，返回现在的第一个（原来的第二个）
                            previous_page = context.pages[0]

                        logger.info(f"🔙 已切换到上一个标签页: {previous_page.url}")
                        return previous_page
                    else:
                        # 只有一个标签页，已经在第一页
                        logger.warning("⚠️  已经在第一页或浏览历史为空")
                        return page

            except Exception as e:
                logger.error(f"❌ BACK操作失败: {e}")
                return page

        elif action == 'FORWARD':
            logger.info("🔜 浏览器前进")

            try:
                await page.go_forward(wait_until='networkidle', timeout=10000)
                logger.info(f"✅ 已前进到下一页: {page.url}")
            except Exception as e:
                logger.error(f"前进失败: {e}")
                # 即使失败也继续，可能是已经在最后一页

            return page

        elif action == 'REFRESH':
            logger.info("🔄 刷新页面")

            try:
                await page.reload(wait_until='networkidle', timeout=10000)
                logger.info(f"✅ 页面已刷新: {page.url}")
            except Exception as e:
                logger.error(f"刷新失败: {e}")

            return page

        elif action == 'CHECK_DOWNLOADS':
            logger.info("📥 查看下载目录")
            # CHECK_DOWNLOADS 会在 _analyze_page 中自动在 prompt 里显示文件列表
            # 这里只需要记录一下操作即可
            logger.info("✅ 下载目录信息已包含在下次决策的 prompt 中")
            return page

        elif action == 'TASK_COMPLETE':
            logger.info("任务完成信号")
            # TASK_COMPLETE不需要执行操作，只是标记完成
            return page

        return page

    async def _handle_batch_execute(
        self,
        page: Page,
        context,
        decision: Dict,
        query: str  # noqa: ARG002 - 保留用于未来扩展
    ):
        """
        处理批量执行请求

        Args:
            page: 当前页面（列表页）
            context: Browser context
            decision: 决策字典
            query: 用户查询
        """
        batch_element_ids = decision.get('batch_element_ids', [])
        batch_description = decision.get('batch_description', '批量操作')

        if not batch_element_ids:
            logger.warning("批量执行缺少element_ids")
            return

        logger.info(f"🚀 开始批量执行: {batch_description}")
        logger.info(f"   目标元素: {batch_element_ids}")

        # 使用批量执行引擎
        results = await self.batch_engine.execute_batch(
            context=context,
            list_page=page,
            element_ids=batch_element_ids,
            description=batch_description,
            use_new_tab=True  # 默认使用新标签页模式
        )

        # 格式化结果
        summary = self._format_batch_results(results)

        # 将结果添加到对话历史，让LLM做最终分析
        self.conversation_history.append({
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": f"批量执行完成。\n\n{summary}\n\n请基于这些内容完成任务。"
                }
            ]
        })

        logger.info(f"✅ 批量执行完成，已将结果返回给LLM")

    def _format_batch_results(self, results: List[dict]) -> str:
        """
        将批量执行结果格式化为适合LLM阅读的文本

        Args:
            results: 批量执行结果列表

        Returns:
            格式化的文本摘要
        """
        success_count = sum(1 for r in results if r["status"] == "success")
        total_count = len(results)

        summary = f"批量执行统计: {success_count}/{total_count} 成功\n\n"

        for result in results:
            if result["status"] == "success":
                data = result["data"]
                summary += f"--- 项目 {result['index']} (元素#{result['element_id']}) ---\n"
                summary += f"标题: {data.get('title', 'N/A')}\n"
                summary += f"内容摘要: {data.get('content', '')[:300]}...\n"
                if data.get('pdf_urls'):
                    summary += f"PDF链接: {', '.join(data['pdf_urls'][:3])}\n"
                summary += "\n"
            else:
                summary += f"--- 项目 {result['index']} (失败) ---\n"
                summary += f"错误: {result.get('error', 'Unknown error')}\n\n"

        return summary

    async def _generate_highlighted_html(self, html_content: str, citations: List[str], task_id: int) -> str:
        """
        生成高亮HTML报告
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, 'html.parser')

        # 高亮引用文本
        if not citations:
            citations = []

        for citation in citations:
            if not citation or len(citation) < 10:
                continue

            # 查找包含引用文本的所有文本节点
            for element in soup.find_all(string=lambda text: citation[:50] in text if text else False):
                try:
                    # 替换为高亮版本
                    parent = element.parent
                    if parent:
                        highlighted = str(element).replace(
                            citation,
                            f'<mark style="background-color: yellow; padding: 2px;">{citation}</mark>'
                        )
                        element.replace_with(BeautifulSoup(highlighted, 'html.parser'))
                except:
                    continue

        # 保存HTML
        report_path = self.reports_dir / f"task_{task_id}_report.html"
        report_path.write_text(str(soup), encoding='utf-8')

        return str(report_path)


# 测试函数
async def test_browser_agent():
    """测试浏览器代理"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("错误：未设置 OPENAI_API_KEY")
        return

    agent = BrowserAgent(api_key=api_key, max_steps=5)

    result = await agent.execute_task(
        query="国家对于预制菜的定义是什么",
        target_url="https://www.gov.cn",
        task_id=999
    )

    print("="*60)
    print("测试结果:")
    print("="*60)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_browser_agent())
