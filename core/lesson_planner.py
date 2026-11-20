"""Business logic for lesson planning"""

import re
from typing import Dict, List, Callable, Optional
from core.agent import UniversityCourseAgent
from core.state import SessionState
from utils.json_parser import extract_json_from_response


class LessonPlannerService:
    """Service class for lesson planning operations"""
    
    def __init__(self):
        self.agent: Optional[UniversityCourseAgent] = None
        self.state = SessionState()
    
    def initialize_agent(self, api_key: str) -> tuple[bool, str]:
        """
        Initialize agent with API key
        
        Returns:
            Tuple of (success, message)
        """
        if not api_key.strip():
            return False, "请输入有效的API Key"
        
        try:
            self.agent = UniversityCourseAgent(api_key)
            self.state.api_key = api_key
            return True, "API Key 配置成功！"
        except Exception as e:
            return False, f"API Key 配置失败：{str(e)}"
    
    async def process_template(self, file_path: str) -> tuple[bool, str, Dict]:
        """
        Process uploaded template file
        
        Returns:
            Tuple of (success, message, keywords)
        """
        if not self.agent:
            return False, "请先配置API Key", {}
        
        try:
            from pathlib import Path
            from utils.template_converter import TemplateConverter
            
            file_extension = Path(file_path).suffix.lower()
            
            # Check if format is supported
            if not TemplateConverter.is_supported_format(file_path):
                return False, f"不支持的文件格式: {file_extension}", {}
            
            # Show conversion status
            conversion_method = TemplateConverter.get_conversion_method()
            if file_extension in ['.doc', '.docx']:
                status_msg = f"📄 检测到Word文档 ({file_extension})\n"
                status_msg += f"🔧 使用转换方式: {conversion_method}\n"
                status_msg += f"⏳ 正在转换为图片进行分析...\n"
            else:
                status_msg = f"🖼️ 检测到图片文件 ({file_extension})\n"
                status_msg += f"⏳ 正在分析模板结构...\n"
            
            # Extract template keywords
            keywords = self.agent.extract_template_keywords(file_path)
            
            # Check if using default template
            if not keywords or keywords == self.agent._get_default_template_structure():
                if file_extension in ['.doc', '.docx']:
                    status_msg += "\n⚠️ Word文档转换可能不完整\n"
                    status_msg += f"💡 建议: 将文档另存为图片格式或安装 aspose-words\n"
                status_msg += "📋 已使用默认模板结构继续\n"
            else:
                status_msg += f"\n✅ 成功解析模板结构\n"
            
            self.state.template_uploaded = True
            self.state.template_keywords = keywords
            self.state.template_file_path = file_path
            
            return True, status_msg, keywords
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"❌ 模板解析失败: {str(e)}", {}
    
    def extract_course_info_from_text(self, text: str) -> Dict:
        """Extract course information from user input"""
        course_info = {}
        
        patterns = {
            'subject': r'(?:课程名称|科目|课程)[:：]?\s*[《]?([^，。；\n《》]+)[》]?',
            'course_type': r'(?:课程性质|类型)[:：]?\s*([^，。；\n]+)',
            'total_lessons': r'(?:课时|次课|讲)[:：]?\s*(\d+)',
            'credits': r'(?:学分)[:：]?\s*(\d+)',
            'major': r'(?:专业|学院)[:：]?\s*([^，。；\n]+)',
            'grade': r'(?:年级|学历)[:：]?\s*([^，。；\n]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                if key == 'subject':
                    subject = match.group(1).strip()
                    subject = subject.replace('《', '').replace('》', '')
                    course_info[key] = subject
                elif key in ['total_lessons', 'credits']:
                    course_info[key] = int(match.group(1))
                else:
                    course_info[key] = match.group(1).strip()
        
        return course_info
    
    async def analyze_user_intent(self, message: str) -> Dict:
        """Analyze user intent using LLM"""
        if not self.agent:
            return {}
        
        from langchain_core.messages import HumanMessage
        
        intent_prompt = f"""
        分析用户的输入，判断用户的意图并提取关键信息。
        
        用户输入：{message}
        
        当前状态：
        - 已上传模板：{self.state.template_uploaded}
        - 已有课程信息：{bool(self.state.course_info)}
        - 已生成大纲：{self.state.outline_generated}
        
        请以JSON格式返回：
        {{
            "course_info": {{
                "subject": "课程名称（如有）",
                "course_type": "课程性质（如有）",
                "total_lessons": 课时数（整数，如有）,
                "credits": 学分（整数，如有）,
                "major": "专业（如有）",
                "grade": "年级（如有）"
            }},
            "should_generate": true/false
        }}
        """
        
        try:
            response = await self.agent.llm_outline.ainvoke([HumanMessage(content=intent_prompt)])
            intent_result = extract_json_from_response(response.content)
            
            # 处理course_info中的默认值：当课时或学分为0时，强制改为2
            if intent_result and 'course_info' in intent_result:
                course_info = intent_result['course_info']
                
                # 如果total_lessons为0或不存在，强制设为2
                if not course_info.get('total_lessons') or course_info.get('total_lessons', 0) == 0:
                    course_info['total_lessons'] = 2
                    print(f"⚠️  课时数为0，已自动设置为2")
                
                # 如果credits为0或不存在，强制设为2
                if not course_info.get('credits') or course_info.get('credits', 0) == 0:
                    course_info['credits'] = 2
                    print(f"⚠️  学分为0，已自动设置为2")
                
                # 确保是整数类型
                if 'total_lessons' in course_info:
                    course_info['total_lessons'] = int(course_info['total_lessons'])
                if 'credits' in course_info:
                    course_info['credits'] = int(course_info['credits'])
            
            return intent_result
        except Exception as e:
            print(f"Intent analysis failed: {e}")
            return {}
    
    async def generate_outline(self) -> tuple[bool, str]:
        """
        Generate course outline
        
        Returns:
            Tuple of (success, message)
        """
        if not self.state.course_info.get('subject'):
            return False, "❌ 请先提供课程基本信息"
        
        try:
            outline = await self.agent.plan_university_course_outline(
                self.state.course_info,
                self.state.requirements
            )
            
            if "error" in outline:
                return False, f"❌ {outline['error']}"
            
            self.state.outline_generated = True
            
            result = f"✅ 课程大纲生成完成！\n\n"
            result += f"📚 课程：{outline['course_info']['course_name']}\n"
            result += f"📊 学分学时：{outline['course_info']['credits']}学分 / {outline['course_info']['total_hours']}学时\n"
            result += f"🎯 共 {len(outline['lessons'])} 次课\n"
            
            return True, result
            
        except Exception as e:
            return False, f"❌ 大纲生成失败：{str(e)}"
    
    async def generate_all_lessons(self, progress_callback: Callable = None) -> tuple[bool, str, List[str]]:
        """
        Generate all lesson plans
        
        Returns:
            Tuple of (success, message, lesson_plans)
        """
        if not self.state.outline_generated:
            return False, "❌ 请先生成课程大纲", []
        
        try:
            lesson_plans = await self.agent.generate_all_lesson_plans(
                self.state.requirements,
                progress_callback
            )
            
            if not lesson_plans or "请先上传模板" in lesson_plans[0]:
                return False, "❌ 教案生成失败，请检查模板和大纲", []
            
            self.state.lesson_plans = lesson_plans
            
            result = f"✅ 成功生成 {len(lesson_plans)} 个完整的大学教案！\n\n"
            result += f"📁 所有教案均按照大学教学规范编写\n"
            
            return True, result, lesson_plans
        
        except Exception as e:
            return False, f"❌ 教案生成失败：{str(e)}", []
    
    def get_lesson_preview(self, max_plans: int = 3, max_chars: int = 800) -> str:
        """Get preview of generated lesson plans"""
        if not self.agent or not self.agent.lesson_plans:
            return "暂无教案内容"
        
        display_content = "# 教案预览\n\n"
        
        for i, plan in enumerate(self.agent.lesson_plans[:max_plans]):
            display_content += f"\n\n---\n\n## 第 {i+1} 次课教案\n\n"
            preview_text = plan[:max_chars] if len(plan) > max_chars else plan
            display_content += preview_text
            if len(plan) > max_chars:
                display_content += "\n\n...(内容较长，已省略)\n"
        
        if len(self.agent.lesson_plans) > max_plans:
            display_content += f"\n\n---\n\n还有 {len(self.agent.lesson_plans) - max_plans} 个教案未显示"
        
        return display_content