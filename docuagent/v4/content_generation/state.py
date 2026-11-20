"""
内容生成工作流的状态定义
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldAnalysis:
    """字段分析结果"""
    
    placeholder: str  # 占位符名称
    field_type: str  # 字段类型：basic_info, objective, content, method, assessment
    content_type: str  # 内容类型描述
    
    # 长度要求
    length_requirement: Dict[str, int]  # {"min_chars": 50, "max_chars": 300, "target_items": 3}
    
    # 生成策略
    style: str  # formal, casual, structured_list, paragraph
    generation_strategy: str  # direct_mapping, structured_list, paragraph_generation, etc.
    
    # 依赖关系
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他字段
    priority: int = 5  # 生成优先级 (1-10, 越小越优先)
    
    # 上下文信息
    location_context: Optional[str] = None  # 位置上下文
    surrounding_text: Optional[str] = None  # 周围的文本
    
    # 原始标注
    annotation: Optional[Dict] = None


@dataclass
class GeneratedField:
    """生成的字段内容"""
    
    placeholder: str  # 占位符名称
    content: str  # 生成的内容
    
    # 元数据
    char_count: int = 0
    word_count: int = 0
    item_count: int = 0  # 如果是列表
    
    # 质量指标
    quality_score: float = 0.0  # 0.0-1.0
    passed_checks: bool = True
    
    # 生成信息
    generation_time: Optional[str] = None
    retry_count: int = 0


@dataclass
class ContentGenerationState:
    """内容生成工作流的状态"""
    
    # ========== 输入数据 ==========
    annotations: List[Dict] = field(default_factory=list)  # 所有标注
    user_input: Dict[str, Any] = field(default_factory=dict)  # 用户提供的信息
    manifest: Dict = field(default_factory=dict)  # 文档结构元数据
    markdown_path: str = ""  # Markdown 模板路径
    kb_insights: str = ""  # 知识库洞察（来自历史经验）
    doc_type: str = "task_proposal"  # 文档类型（用于字段约束验证）

    # ========== 工作状态 ==========
    # 字段分析
    analyzed_fields: List[FieldAnalysis] = field(default_factory=list)
    field_order: List[str] = field(default_factory=list)  # 生成顺序
    
    # 内容生成
    current_index: int = 0  # 当前处理的字段索引（单个模式）
    generated_content: Dict[str, GeneratedField] = field(default_factory=dict)
    
    # 批量生成相关
    field_batches: List[List[FieldAnalysis]] = field(default_factory=list)  # 字段批次
    current_batch_index: int = 0  # 当前批次索引
    
    # 进度追踪
    total_fields: int = 0
    completed_fields: int = 0
    failed_fields: List[str] = field(default_factory=list)
    
    # ========== 控制标志 ==========
    is_complete: bool = False
    error_message: Optional[str] = None
    
    # ========== 配置 ==========
    max_retries: int = 3  # 每个字段的最大重试次数
    batch_mode: bool = True  # 是否使用批量生成模式
    batch_size: int = 5  # 批量生成的字段数
    
    def get_progress(self) -> float:
        """获取生成进度百分比"""
        if self.total_fields == 0:
            return 0.0
        return (self.completed_fields / self.total_fields) * 100
    
    def get_current_field(self) -> Optional[FieldAnalysis]:
        """获取当前待处理的字段"""
        if self.current_index < len(self.analyzed_fields):
            return self.analyzed_fields[self.current_index]
        return None
    
    def get_generated_content_dict(self) -> Dict[str, str]:
        """获取已生成内容的简单字典（placeholder -> content）"""
        return {
            placeholder: field.content
            for placeholder, field in self.generated_content.items()
        }
    
    def get_dependencies_content(self, dependencies: List[str]) -> Dict[str, str]:
        """获取依赖字段的已生成内容"""
        return {
            dep: self.generated_content[dep].content
            for dep in dependencies
            if dep in self.generated_content
        }
