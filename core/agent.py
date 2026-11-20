"""Core agent for university course planning - 修复版本"""

import json
import base64
import re
from typing import Dict, List
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_community.chat_models import ChatTongyi

from config import DEFAULT_TEMPLATE_STRUCTURE
from utils.template_converter import TemplateConverter
from utils.json_parser import extract_json_from_response


class UniversityCourseAgent:
    """Main agent for university lesson plan generation"""
    
    def __init__(self, api_key: str):
        """Initialize the university course agent"""
        self.api_key = api_key
        # 大纲生成使用最好的模型
        self.llm_outline = ChatTongyi(
            dashscope_api_key=api_key,
            model_name="qwen-plus"
        )
        # 教案生成使用快速的模型
        self.llm_lesson = ChatTongyi(
            dashscope_api_key=api_key,
            model_name="qwen-turbo"
        )
        # 通用对话使用中等模型
        self.llm_chat = ChatTongyi(
            dashscope_api_key=api_key,
            model_name="qwen-turbo"
        )
        self.vlm = ChatTongyi(
            dashscope_api_key=api_key,
            model_name="qwen-vl-plus"
        )
        self.conversation_history = []
        self.template_keywords = {}
        self.course_outline = None
        self.lesson_plans = []
        self.course_requirements = ""
        # 模板类型相关
        self.template_mode = "text"  # "text" 或 "tags"
        self.template_file_path = None
        self.detected_tags = []

    def extract_template_keywords(self, file_path: str) -> Dict:
        """Extract template keywords using VLM (supports DOC/DOCX conversion)"""
        try:
            # Check file type
            file_extension = Path(file_path).suffix.lower()
            image_paths = []
            
            if file_extension in ['.doc', '.docx']:
                print(f"🔍 检测到Word文档，开始检测模板类型...")
                print(f"   文件路径: {file_path}")
                print(f"   文件大小: {Path(file_path).stat().st_size / 1024:.2f} KB")
                
                # ========== 新增：检测XML标签 ==========
                try:
                    from utils.template_filler import WordTemplateFiller
                    filler = WordTemplateFiller()
                    tag_info = filler.check_template_tags(file_path)
                    
                    if tag_info.get('success') and tag_info.get('has_tags'):
                        # 发现XML标签
                        self.template_mode = "tags"
                        self.template_file_path = file_path
                        self.detected_tags = tag_info.get('recognized_tags', [])
                        
                        print(f"✅ 检测到智能标签模板！")
                        print(f"   - 识别的标签: {len(self.detected_tags)} 个")
                        print(f"   - 未识别的标签: {len(tag_info.get('unrecognized_tags', []))} 个")
                        
                        if tag_info.get('unrecognized_tags'):
                            print(f"   ⚠️  未识别标签: {tag_info.get('unrecognized_tags')[:5]}")
                        
                        # 返回标签信息作为模板结构
                        return {
                            'template_type': 'xml_tags',
                            'mode': 'tags',
                            'tags': self.detected_tags,
                            'tag_info': tag_info
                        }
                    else:
                        print(f"📝 未检测到XML标签，使用传统视觉识别方式")
                        self.template_mode = "text"
                except Exception as tag_error:
                    import traceback
                    print(f"⚠️  标签检测失败，使用传统方式")
                    print(f"   错误类型: {type(tag_error).__name__}")
                    print(f"   错误信息: {str(tag_error)}")
                    if "unsupport" in str(tag_error).lower() or "format" in str(tag_error).lower():
                        print(f"   💡 提示: 文件可能不是标准的.docx格式")
                        print(f"   💡 建议: 用Microsoft Word或WPS重新保存为.docx")
                    self.template_mode = "text"
                
                # ========== 传统视觉识别方式 ==========
                print(f"🖼️  转换为图片进行视觉分析...")
                image_paths = TemplateConverter.convert_to_images(file_path)
                
                # 修改点1: 正确保存图片路径列表
                with open("image_paths.txt", "w", encoding="utf-8") as file:
                    for path in image_paths:
                        file.write(f"{str(path)}\n")  # 确保每个路径单独写入
                
                if not image_paths:
                    print("Document conversion failed, returning default template structure")
                    return DEFAULT_TEMPLATE_STRUCTURE
                    
            elif file_extension in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                image_paths = [file_path]
                self.template_mode = "text"
            else:
                print(f"Unsupported file format: {file_extension}")
                self.template_mode = "text"
                return DEFAULT_TEMPLATE_STRUCTURE
            
            # 修改点2: 分析所有页面图片
            if image_paths:
                result = self._analyze_all_template_images(image_paths)
                result['mode'] = 'text'  # 标记为文本模式
                return result
            else:
                return DEFAULT_TEMPLATE_STRUCTURE
                
        except Exception as e:
            print(f"Template parsing error: {e}")
            self.template_mode = "text"
            return DEFAULT_TEMPLATE_STRUCTURE
    
    def _analyze_all_template_images(self, image_paths: List[str]) -> Dict:
        """
        修改点3: 新方法 - 分析所有模板图片页面（两步提示法）
        分析多页模板图片，综合提取完整结构信息
        """
        try:
            # 准备所有图片的base64数据
            images_data = []
            for i, image_path in enumerate(image_paths):
                try:
                    with open(image_path, "rb") as f:
                        image_data = base64.b64encode(f.read()).decode()
                        images_data.append({
                            "page": i + 1,
                            "data": image_data
                        })
                    print(f"成功读取第 {i+1} 页图片")
                except Exception as e:
                    print(f"读取第 {i+1} 页图片失败: {e}")
                    continue
            
            if not images_data:
                print("没有成功读取任何图片，使用默认模板")
                return DEFAULT_TEMPLATE_STRUCTURE
            
            # 构建包含所有图片的消息内容
            message_content_base = []
            for img_data in images_data:
                message_content_base.append({
                    "image": f"data:image/png;base64,{img_data['data']}"
                })
            
            # 【可选】步骤1：先让VLM详细描述看到的内容（增强理解）
            print("步骤1: 让VLM详细描述模板结构...")
            description_prompt = f"""
            请详细描述这{len(images_data)}页教案模板图片中的内容：
            
            1. **封面信息**：列出封面上的所有字段
            2. **表格结构**：
               - 表格有多少个主要部分？
               - 每个部分的标题是什么？
               - 每个部分下有哪些子环节？
               - 表格有几列？每列的标题是什么？
            3. **教学过程分几个阶段**：
               - 每个阶段的名称是什么？
               - 每个阶段包含哪些具体环节？
               - 哪些环节标注了时间？时间是多少？
            4. **特殊字段**：
               - 是否有思政相关内容？
               - 是否提到AI助教或智慧课堂？
               - 教学目标如何分类？
            
            请用文字详细描述，不要遗漏任何字段名称。
            """
            
            from langchain_core.messages import SystemMessage
            system_msg = SystemMessage(content="""你是一个专业的教案模板分析专家。
            请仔细观察表格的每一个单元格，包括：
            - 表格的行标题和列标题
            - 单元格中的文字内容和示例
            - 时间标注（如"5分钟"、"X分钟"）
            - 环节的层级关系（主环节和子环节）
            
            描述时要详细、准确，不要遗漏任何字段。""")
            
            message_content_step1 = [{"text": description_prompt}] + message_content_base
            description_response = self.vlm.invoke([system_msg, HumanMessage(content=message_content_step1)])
            
            # Log usage
            try:
                from utils.llm_logger import log_llm_call_async
                log_llm_call_async(feature='vlm_detection', model_name='qwen-vl-plus')
            except Exception: pass

            print(f"VLM描述结果: {description_response.content[:500]}...")
            
            # 保存描述结果 - 正确提取文本内容
            if isinstance(description_response.content, list):
                desc_text = ""
                for item in description_response.content:
                    if isinstance(item, dict) and 'text' in item:
                        desc_text += item['text']
                    elif isinstance(item, str):
                        desc_text += item
            else:
                desc_text = str(description_response.content)
            
            with open("vlm_description.txt", "w", encoding="utf-8") as file:
                file.write(desc_text)
            
            # 步骤2：基于描述结果，要求结构化输出
            print("步骤2: 要求VLM输出结构化JSON...")
            
            # 构建包含所有页面的详细分析提示
            prompt = f"""
            请仔细分析这个大学教案模板的所有{len(images_data)}页图片。这是一个表格式教案模板，请按照表格中的实际字段和层级结构提取信息。

            **分析要求**：
            1. 仔细观察表格的每一行，提取所有字段名称
            2. 注意字段的层级关系（如"课前预习"下有多个子环节）
            3. 提取示例内容和时间标注（如"5分钟"、"X分钟"）
            4. 注意表格单元格的列结构（教学内容、教师活动、学生活动、设计意图等）
            5. 识别所有教学环节的名称和顺序

            请综合所有页面的内容，以JSON格式返回详细的模板结构：

            {{
                "template_metadata": {{
                    "institution": "学校名称（从页眉或LOGO识别）",
                    "template_type": "教案类型",
                    "academic_year": "学年学期信息",
                    "pages_analyzed": {len(images_data)}
                }},
                
                "cover_page": {{
                    "basic_fields": ["列出封面上的所有字段，如：课程名称、课程类别、学分、学时、授课教师、教学单位、授课班级、使用教材等"]
                }},
                
                "main_table_structure": {{
                    "header_section": {{
                        "time_info": ["授课时间的所有子字段，如：年月日、第几周、星期几、第几节"],
                        "chapter_info": ["授课章节"]
                    }},
                    
                    "teaching_objectives_section": {{
                        "section_name": "本章节教学目标（识别准确的标题）",
                        "objective_categories": {{
                            "category_1": "思政育人目标",
                            "category_2": "知识目标",
                            "category_3": "能力目标",
                            "category_4": "教学目标4... （如果有其他分类，请列出完整名称）"
                        }},
                        "has_ideological_elements": true,
                        "ideological_section_name": "思政元素要点"
                    }},
                    
                    "key_difficult_section": {{
                        "teaching_key_points": {{
                            "field_name": "教学重点",
                            "has_description": true,
                            "has_solution": true,
                            "columns": ["教学重点描述", "解决措施"]
                        }},
                        "teaching_difficult_points": {{
                            "field_name": "教学难点",
                            "has_description": true,
                            "has_solution": true,
                            "columns": ["教学难点描述", "解决措施"]
                        }}
                    }},
                    
                    "method_resource_section": {{
                        "teaching_methods": {{
                            "field_name": "教学方法",
                            "has_sub_columns": true,
                            "columns": ["教法", "学法"]
                        }},
                        "teaching_resources": {{
                            "field_name": "教学资源",
                            "example_items": ["从模板中提取的示例，如：智慧课堂平台、AI助教等"],
                            "format_description": "资源描述的格式要求"
                        }}
                    }},
                    
                    "teaching_process_section": {{
                        "section_name": "教学内容及过程",
                        
                        "phase_1_before_class": {{
                            "phase_name": "课前预习",
                            "stage_1": {{
                                "stage_name": "案例启思",
                                "columns": ["教学内容", "教师活动", "学生活动", "设计意图"],
                                "teacher_activities_example": ["发布预习案例", "设计思考问题", "试题评分、评价", "调整教学策略"],
                                "student_activities_example": ["观看案例视频", "完成思考题", "查看评分、评价"],
                                "time_allocation": "是否标注时间"
                            }},
                            "stage_2": {{
                                "stage_name": "自主学习",
                                "has_numbered_items": true,
                                "content_structure": "预习内容1... 2... ",
                                "columns": ["预习内容（带编号）", "教师活动（带编号）", "学生活动（带编号）", "设计意图"],
                                "teacher_activities_example": ["发布课前任务", "推送理论资源", "推送案例视频"],
                                "student_activities_example": ["查看课前任务", "学习理论资源", "..."]
                            }}
                        }},
                        
                        "phase_2_in_class": {{
                            "phase_name": "课中学创",
                            "stages": [
                                {{
                                    "stage_name": "新课导入",
                                    "time_minutes": "5分钟",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"],
                                    "content_description": "案例引入，展示XX的真实案例",
                                    "teacher_activity": "通过XX真实案例，引入本次课程的任务",
                                    "student_activity": "了解案例内容，明确本次课程的任务/要求",
                                    "design_intent": "用真实案例激发学生兴趣，自然引入课题"
                                }},
                                {{
                                    "stage_name": "预习反馈",
                                    "time_minutes": "X分钟",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }},
                                {{
                                    "stage_name": "新课讲授",
                                    "time_minutes": "X分钟",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }},
                                {{
                                    "stage_name": "实践",
                                    "time_minutes": "X分钟",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }},
                                {{
                                    "stage_name": "展示",
                                    "time_minutes": "X分钟",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }},
                                {{
                                    "stage_name": "评价",
                                    "time_minutes": "X分钟",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }}
                            ]
                        }},
                        
                        "phase_3_after_class": {{
                            "phase_name": "课后拓展",
                            "stages": [
                                {{
                                    "stage_name": "课后作业",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }},
                                {{
                                    "stage_name": "阅读延伸",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }},
                                {{
                                    "stage_name": "......（如果还有其他环节，请列出）",
                                    "columns": ["教学内容", "教师活动", "学生活动", "设计意图"]
                                }}
                            ]
                        }}
                    }},
                    
                    "teaching_reflection_section": {{
                        "section_name": "教学反思",
                        "sub_sections": [
                            {{
                                "name": "目标效果",
                                "description": "反思教学目标的达成情况"
                            }},
                            {{
                                "name": "反思改进",
                                "description": "反思教学过程中的问题和改进措施"
                            }}
                        ]
                    }}
                }},
                
                "format_requirements": {{
                    "document_format": "Word/PDF",
                    "font": {{
                        "primary": "主要字体名称",
                        "size": "字号",
                        "title_format": "标题字体格式"
                    }},
                    "paragraph": {{
                        "indent": "缩进要求",
                        "spacing": "行距",
                        "alignment": "对齐方式"
                    }},
                    "table": {{
                        "border_style": "边框样式",
                        "header_format": "表头格式",
                        "content_alignment": "内容对齐",
                        "cell_structure": "单元格合并情况描述"
                    }},
                    "page_layout": {{
                        "margins": "页边距",
                        "header_footer": "页眉页脚内容"
                    }}
                }},
                
                "special_features": [
                    "列出模板的特色功能，如：AI助教应用、智慧课堂平台、思政元素融入、三段式教学流程等"
                ]
            }}
            
            **参考刚才的描述结果**：
            {description_response.content[:1000]}
            
            **重要提示**：
            1. 请严格按照表格中的实际字段名称提取，不要改动或简化
            2. 特别注意"课前预习"、"课中学创"、"课后拓展"三个阶段的完整结构
            3. 识别所有环节名称（如"案例启思"、"自主学习"等）
            4. 注意时间标注的差异（"5分钟" vs "X分钟"）
            5. 提取表格列结构（教学内容、教师活动、学生活动、设计意图）
            6. 提取模板中的示例内容（如"智慧课堂平台：发布XX案例...""AI助教：提供知识问答..."）
            7. 如果某些字段不清晰，请在对应位置注明"待确认"
            8. 只返回JSON，不要添加markdown代码块标记或其他说明文字
            """
            
            # 构建包含所有图片的消息内容
            message_content_step2 = [{"text": prompt}] + message_content_base
            
            print(f"正在使用VLM分析 {len(images_data)} 页模板图片（结构化输出）...")
            response = self.vlm.invoke([system_msg, HumanMessage(content=message_content_step2)])
            
            # 修改点4: 确保响应内容正确保存
            # 正确提取文本内容
            if isinstance(response.content, list):
                text_content = ""
                for item in response.content:
                    if isinstance(item, dict) and 'text' in item:
                        text_content += item['text']
                    elif isinstance(item, str):
                        text_content += item
            else:
                text_content = str(response.content)
            
            with open("vlm_response.txt", "w", encoding="utf-8") as file:
                file.write(text_content)  # 保存实际的文本内容
            
            # 提取JSON结果
            result = extract_json_from_response(response.content)
            
            if result:
                print(f"成功分析模板，提取了 {len(result.keys())} 个结构字段")
                self.template_keywords = result
                return result
            else:
                print("JSON提取失败，使用默认模板")
                return DEFAULT_TEMPLATE_STRUCTURE
            
        except Exception as e:
            print(f"Image analysis error: {e}")
            import traceback
            traceback.print_exc()  # 打印详细错误堆栈
            return DEFAULT_TEMPLATE_STRUCTURE
    
    def _analyze_template_image(self, image_path: str) -> Dict:
        """
        保留原方法（向后兼容），但现在调用新的多图片分析方法
        """
        return self._analyze_all_template_images([image_path])
        
    def _get_default_template_structure(self) -> Dict:
        """返回默认的大学教案模板结构"""
        from config import DEFAULT_TEMPLATE_STRUCTURE
        return DEFAULT_TEMPLATE_STRUCTURE
    
    async def plan_university_course_outline(self, course_info: Dict, requirements: str = "") -> Dict:
        """Plan university course outline"""
        subject = course_info.get('subject', '')
        course_type = course_info.get('course_type', '专业课')
        total_lessons = course_info.get('total_lessons', 16)
        credits = course_info.get('credits', 3)
        major = course_info.get('major', '')
        grade = course_info.get('grade', '本科')
        
        # 当课时或学分为0时，强制改为2
        if not total_lessons or total_lessons == 0:
            total_lessons = 2
            print(f"⚠️  课时数为0，已自动设置为2")
        if not credits or credits == 0:
            credits = 2
            print(f"⚠️  学分为0，已自动设置为2")
        
        # 确保是整数类型
        total_lessons = int(total_lessons)
        credits = int(credits)
        
        # 验证课程信息
        if not subject:
            return {"error": "课程名称不能为空"}
        if total_lessons <= 0:
            return {"error": f"总课时数必须大于0，当前值: {total_lessons}"}
        if credits <= 0:
            return {"error": f"学分必须大于0，当前值: {credits}"}
        
        print(f"📝 生成课程大纲:")
        print(f"   课程名称: {subject}")
        print(f"   课程性质: {course_type}")
        print(f"   学分: {credits}")
        print(f"   总课时: {total_lessons}")
        
        prompt = f"""
请为{grade}{major}专业的《{subject}》({course_type})制定{total_lessons}次课的详细教学大纲。制定过程中不要出现学校名称。

**重要要求**：
1. 必须生成完整的{total_lessons}次课的详细大纲
2. lessons数组必须包含{total_lessons}个课时对象，不能为空
3. 每个课时必须包含lesson_number、title、type、hours等完整信息
4. 必须返回有效的JSON格式，不要有任何说明文字

课程基本信息：
- 课程名称：{subject}
- 课程性质：{course_type}
- 学分：{credits}学分
- 总学时：{total_lessons * 2}学时（按2学时/次计算，共{total_lessons}次课）
- 授课对象：{grade}{major}专业学生

特殊要求：{requirements}

请按照大学教学规范，生成符合以下JSON格式的课程大纲，**必须返回完整的JSON，lessons数组必须包含{total_lessons}个课时**：
        {{
            "course_info": {{
                "course_name": "{subject}",
                "course_type": "{course_type}",
                "credits": {credits},
                "total_hours": {total_lessons * 2},
                "target_students": "{grade}{major}专业",
                "prerequisites": "前置课程要求"
            }},
            "course_objectives": {{
                "knowledge_objectives": ["知识目标1", "知识目标2"],
                "ability_objectives": ["能力目标1", "能力目标2"],
                "quality_objectives": ["素质目标1", "素质目标2"]
            }},
            "lessons": [
                {{
                    "lesson_number": 1,
                    "title": "第一章 课程标题",
                    "type": "理论课/实践课/讨论课",
                    "hours": 2,
                    "knowledge_points": ["知识点1", "知识点2"],
                    "key_points": ["教学重点1", "教学重点2"],
                    "difficult_points": ["教学难点1", "教学难点2"],
                    "teaching_methods": ["教学方法1", "教学方法2"],
                    "learning_outcomes": "预期学习成果"
                }}
            ],
            "assessment_plan": {{
                "formative_assessment": "过程性评价方案",
                "summative_assessment": "终结性评价方案",
                "assessment_ratio": "评价比例分配"
            }}
        }}
        
        只返回JSON，不要有任何其他说明文字。
        """
        
        print(f"   📡 发送请求到通义千问 (qwen-plus)... ")
        response = await self.llm_outline.ainvoke([HumanMessage(content=prompt)])
        
        # Log usage
        try:
            from utils.llm_logger import log_llm_call_async
            log_llm_call_async(feature='v5_generation', model_name='qwen-plus')
        except Exception: pass

        # 保存完整响应用于调试
        try:
            # 正确提取文本内容
            if isinstance(response.content, list):
                outline_text = ""
                for item in response.content:
                    if isinstance(item, dict) and 'text' in item:
                        outline_text += item['text']
                    elif isinstance(item, str):
                        outline_text += item
            else:
                outline_text = str(response.content)
            
            with open("outline_response.txt", "w", encoding="utf-8") as f:
                f.write(outline_text)
            print("💾 大纲响应已保存到 outline_response.txt")
        except:
            pass
        
        try:
            # 使用统一的 JSON 提取函数
            from utils.json_parser import extract_json_from_response
            self.course_outline = extract_json_from_response(response.content)
            
            # 验证是否成功提取
            if not self.course_outline:
                print(f"❌ JSON提取失败，返回了空值")
                print(f"原始响应前500字符：{response.content[:500]}")
                return {"error": "大纲生成失败，模型返回格式不正确"}
            
            # 检查必要字段
            if "course_info" not in self.course_outline:
                print(f"❌ 缺少course_info字段")
                print(f"提取的结构字段: {list(self.course_outline.keys())}")
                return {"error": "大纲生成失败，缺少课程信息"}
            
            # 检查lessons字段
            lessons = self.course_outline.get('lessons', [])
            if not lessons or len(lessons) == 0:
                print(f"⚠️  警告: lessons数组为空或不存在")
                print(f"课程大纲结构: {list(self.course_outline.keys())}")
                print(f"lessons类型: {type(lessons)}")
                
                # 尝试修复：如果是空数组，尝试从响应中重新提取
                print(f"🔧 尝试重新解析响应...")
                # 保存失败的大纲以便调试
                try:
                    with open("failed_outline.json", "w", encoding="utf-8") as f:
                        import json
                        json.dump(self.course_outline, f, ensure_ascii=False, indent=2)
                    print("💾 失败的大纲结构已保存到 failed_outline.json")
                except:
                    pass
                
                return {"error": f"大纲生成失败：lessons数组为空。请检查课程信息是否正确，确保总课时数(total_lessons)大于0"}
            
            # 验证lessons数组中的内容
            print(f"✅ 成功提取课程大纲")
            print(f"   - 课程名称: {self.course_outline.get('course_info', {}).get('course_name', 'N/A')}")
            print(f"   - lessons数量: {len(lessons)}")
            print(f"   - 第一个课时: {lessons[0].get('title', 'N/A') if lessons else 'N/A'}")
            
            return self.course_outline
            
        except Exception as e:
            print(f"大纲生成错误: {e}")
            print(f"响应内容前500字符: {response.content[:500]}")
            import traceback
            traceback.print_exc()
            return {"error": f"大纲生成失败: {str(e)}"}


    async def generate_lesson_plan_for_tags(self, lesson_info: Dict, detected_tags: List[str],
                                            additional_requirements: str = "") -> Dict:
        """为标签模式生成JSON结构化数据
        
        Args:
            lesson_info: 课程信息
            detected_tags: 检测到的标签列表
            additional_requirements: 附加要求
            
        Returns:
            Dict: 结构化的教案数据,键名与标签对应
        """
        print(f"📊 使用标签模式生成教案（检测到 {len(detected_tags)} 个标签）")
        
        prompt = f"""
请根据以下信息生成一份完整的大学教案内容，以JSON格式返回。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【一、课程基本信息】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
课程名称：{self.course_outline.get('course_info', {}).get('course_name', '')}
课程性质：{self.course_outline.get('course_info', {}).get('course_type', '')}
授课对象：{self.course_outline.get('course_info', {}).get('target_students', '')}

【本次课信息】
章节标题：{lesson_info.get('title', '')}
课程类型：{lesson_info.get('type', '')}
学时：{lesson_info.get('hours', 2)}学时
知识点：{', '.join(lesson_info.get('knowledge_points', []))}
教学重点：{', '.join(lesson_info.get('key_points', []))}
教学难点：{', '.join(lesson_info.get('difficult_points', []))}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【二、需要填充的标签列表】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{json.dumps(detected_tags, ensure_ascii=False)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【三、附加要求】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{additional_requirements if additional_requirements else "无特殊要求"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【四、输出要求】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

请为上述标签列表中的每个标签生成对应的内容，返回JSON格式：

{{
    "course_name": "课程名称",
    "lesson_title": "本次课标题",
    "chapter_section": "授课章节",
    "teaching_hours": "2",
    "lesson_number": "1",
    
    "ideological_goals": "思政育人目标的详细内容...",
    "knowledge_goals": "知识目标的详细内容...",
    "ability_goals": "能力目标的详细内容...",
    "ideological_elements": "思政元素的详细内容...",
    
    "teaching_focus": "教学重点的详细内容...",
    "focus_solutions": "教学重点解决措施的详细内容...",
    "teaching_difficulty": "教学难点的详细内容...",
    "difficulty_solutions": "教学难点解决措施的详细内容...",
    
    "teaching_methods": "教法的详细内容...",
    "learning_methods": "学法的详细内容...",
    "teaching_resources": "教学资源的详细内容...",
    
    "preview_content": "课前预习-教学内容...",
    "preview_teacher": "课前预习-教师活动...",
    "preview_student": "课前预习-学生活动...",
    "preview_intention": "课前预习-设计意图...",
    
    ... （为所有检测到的标签生成内容）
}}

**重要规则：**
1. **只返回JSON，不要任何其他文字**
2. **只为检测到的标签生成内容**（不要生成未检测到的标签）
3. 每个标签的内容要详细、具体、可操作
4. 内容要符合大学教学规范
5. 教学过程要分阶段、有时间安排
6. 思政元素要自然融入，不生硬
7. 不包含具体学校名称和教师姓名

现在请生成JSON：
"""
        
        response = await self.llm_lesson.ainvoke([HumanMessage(content=prompt)])
        
        try:
            from utils.json_parser import extract_json_from_response
            lesson_data = extract_json_from_response(response.content)
            
            if not lesson_data:
                print(f"⚠️  JSON提取失败，尝试解析原始内容...")
                print(f"原始响应：{response.content[:500]}")
                return {"error": "教案生成失败，模型返回格式不正确"}
            
            print(f"✅ 成功生成 {len(lesson_data)} 个字段的结构化数据")
            return lesson_data
            
        except Exception as e:
            print(f"❌ 教案生成错误: {e}")
            print(f"响应内容: {response.content[:500]}")
            return {"error": f"教案生成失败: {str(e)}"}
    
    async def generate_university_lesson_plan(self, lesson_info: Dict, template_structure: Dict, 
                                        additional_requirements: str = "") -> str:
        """Generate university lesson plan with dynamic template adaptation - 动态适配版"""
        
        # ========== 动态提取模板结构，不依赖固定字段名 ==========
        main_table = template_structure.get('main_table_structure', {})
        
        # 1. 动态提取教学目标结构
        objectives_section = main_table.get('teaching_objectives_section', {})
        objective_categories = objectives_section.get('objective_categories', {})
        
        # 2. 动态提取教学重难点结构
        key_difficult = main_table.get('key_difficult_section', {})
        
        # 3. 动态提取教学方法和资源
        method_resource = main_table.get('method_resource_section', {})
        
        # 4. 动态提取教学过程（核心 - 不预设结构）
        process_section = main_table.get('teaching_process_section', {})
        
        # 5. 动态提取其他部分
        reflection_section = main_table.get('teaching_reflection_section', {})
        cover_page = template_structure.get('cover_page', {})
        format_req = template_structure.get('format_requirements', {})
        
        # ========== 智能分析教学过程结构（自动识别阶段类型）==========
        def analyze_process_structure(process_section: Dict) -> str:
            """自动分析并生成教学过程描述，不预设固定结构"""
            if not process_section:
                return "（模板未定义教学过程结构，请按常规教学流程设计）"
            
            process_desc = "\n**教学过程结构分析：**\n"
            
            # 遍历所有阶段（phase_1, phase_2, phase_3...）
            for key in sorted(process_section.keys()):
                if key.startswith('phase_'):
                    phase = process_section[key]
                    phase_name = phase.get('phase_name', '未命名阶段')
                    process_desc += f"\n【阶段：{phase_name}】\n"
                    
                    # 识别该阶段的所有环节（stage_1, stage_2 或 stages列表）
                    stages = []
                    
                    # 方式1：枚举式环节 (stage_1, stage_2...)
                    for stage_key in sorted(phase.keys()):
                        if stage_key.startswith('stage_'):
                            stages.append(phase[stage_key])
                    
                    # 方式2：列表式环节 (stages: [...])
                    if 'stages' in phase and isinstance(phase['stages'], list):
                        stages.extend(phase['stages'])
                    
                    # 描述每个环节
                    for i, stage in enumerate(stages, 1):
                        if isinstance(stage, dict):
                            stage_name = stage.get('stage_name', f'环节{i}')
                            time = stage.get('time_minutes', '')
                            columns = stage.get('columns', [])
                            
                            time_str = f"（{time}分钟）" if time and time != 'X' else ""
                            columns_str = f"，字段：{', '.join(columns)}" if columns else ""
                            
                            process_desc += f"  {i}. {stage_name}{time_str}{columns_str}\n"
            
            return process_desc
        
        # ========== 智能提取表格列结构 ==========
        def extract_table_columns(process_section: Dict) -> List[str]:
            """自动提取教学过程表格的列结构"""
            columns_set = set()
            
            for key, phase in process_section.items():
                if not isinstance(phase, dict):
                    continue
                
                # 检查所有环节
                for stage_key, stage in phase.items():
                    if isinstance(stage, dict) and 'columns' in stage:
                        columns_set.update(stage.get('columns', []))
                
                # 检查stages列表
                if 'stages' in phase and isinstance(phase['stages'], list):
                    for stage in phase['stages']:
                        if isinstance(stage, dict) and 'columns' in stage:
                            columns_set.update(stage.get('columns', []))
            
            return list(columns_set) if columns_set else ['教学内容', '教师活动', '学生活动', '设计意图']
        
        # ========== 生成教学过程描述 ==========
        process_desc = analyze_process_structure(process_section)
        table_columns = extract_table_columns(process_section)
        
        # ========== 构建动态prompt ==========
        prompt = f"""
    请根据以下信息生成一份完整的大学教案，**严格遵循提取的模板结构，不要预设固定格式**：

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    【一、课程基本信息】
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    课程名称：{self.course_outline.get('course_info', {}).get('course_name', '')}
    课程性质：{self.course_outline.get('course_info', {}).get('course_type', '')}
    授课对象：{self.course_outline.get('course_info', {}).get('target_students', '')}

    【本次课信息】
    章节标题：{lesson_info.get('title', '')}
    课程类型：{lesson_info.get('type', '')}
    学时：{lesson_info.get('hours', 2)}学时
    知识点：{', '.join(lesson_info.get('knowledge_points', []))}
    教学重点：{', '.join(lesson_info.get('key_points', []))}
    教学难点：{', '.join(lesson_info.get('difficult_points', []))}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    【二、模板结构要求（动态适配）】
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    📄 **模板元信息：**
    {json.dumps(template_structure.get('template_metadata', {}), ensure_ascii=False, indent=2)}

    📄 **封面字段：**
    {json.dumps(cover_page.get('basic_fields', []), ensure_ascii=False)}
    一定要包含章节标题

    📄 **教学目标结构：**
    模板定义的目标类型：
    {json.dumps(objective_categories, ensure_ascii=False, indent=2)}
    是否包含思政元素：{objectives_section.get('has_ideological_elements', False)}
    {f"思政部分名称：{objectives_section.get('ideological_section_name', '')}" if objectives_section.get('has_ideological_elements') else ""}

    📄 **教学重难点结构：**
    {json.dumps(key_difficult, ensure_ascii=False, indent=2)}

    📄 **教学方法与资源结构：**
    {json.dumps(method_resource, ensure_ascii=False, indent=2)}

    📄 **教学过程结构（核心 - 严格遵循）：**
    {process_desc}

    表格列结构：{', '.join(table_columns)}

    📄 **教学反思结构：**
    {json.dumps(reflection_section, ensure_ascii=False, indent=2)}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    【三、附加要求】
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {additional_requirements if additional_requirements else "无特殊要求"}

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    【四、生成规范】
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    请**严格按照上述模板结构**生成完整教案，要求：

    ✅ **结构适配原则：**
    1. 完全按照"教学过程结构"中列出的阶段和环节组织内容
    2. 不要增加或删减模板中定义的任何环节
    3. 严格使用模板定义的字段名称（不要改写或替换）
    4. 表格列必须与"表格列结构"完全一致

    ✅ **内容填充原则：**
    1. 每个环节的内容要具体、可操作
    2. 时间分配要合理（参考模板中标注的时间）
    3. 教师活动和学生活动要对应且具体
    4. 设计意图要说明教学法依据

    ✅ **格式规范：**
    1. 使用Markdown表格展示教学过程
    2. 表格列顺序：{' | '.join(table_columns)}
    3. 不包含具体学校、教师姓名
    4. 专业术语准确，逻辑清晰

    ✅ **输出结构框架：**

    # 教案标题：{lesson_info.get('title', '')}

    ## 一、封面信息
    （按模板定义的字段填写）

    ## 二、教学目标
    （按模板定义的目标类型分类）

    ## 三、教学重难点
    （按模板定义的结构填写，包含描述和解决措施）

    ## 四、教学方法与资源
    （按模板定义的结构填写）

    ## 五、教学过程
    （**核心部分 - 必须严格按照上述"教学过程结构"生成**）

    ### 【阶段名称】
    #### 环节1：环节名称（X分钟）
    | {' | '.join(table_columns)} |
    |{'|'.join(['---' for _ in table_columns])}|
    | [填写具体内容] |

    （按模板定义的所有阶段和环节依次展开）

    ## 六、教学反思
    （按模板定义的反思结构填写）

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    【五、重要提示】
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ⚠️ **务必严格遵循模板结构，这是最重要的要求！**
    ⚠️ 不要凭经验添加模板中没有的环节
    ⚠️ 不要修改模板中定义的字段名称
    ⚠️ 表格列数和列名必须与模板完全一致
    ⚠️ 教学过程的阶段和环节顺序要与模板一致

    现在请开始生成教案：
    """
        
        response = await self.llm_lesson.ainvoke([HumanMessage(content=prompt)])
        return response.content

    async def generate_all_lesson_plans(self, additional_requirements: str = "", 
                                  progress_callback=None) -> List:
        """批量生成所有教案，支持实时预览
        
        Returns:
            List: 根据模板类型返回不同格式
                  - tags模式: 返回Dict列表（每个教案是字典）
                  - text模式: 返回str列表（每个教案是Markdown文本）
        """
        if not self.course_outline or not self.template_keywords:
            print(f"❌ 缺少必要数据: course_outline={bool(self.course_outline)}, template_keywords={bool(self.template_keywords)}")
            return ["请先上传模板并生成课程大纲"]
        
        lesson_plans = []
        lessons = self.course_outline.get('lessons', [])
        total_lessons = len(lessons)
        
        # 调试信息
        print(f"📊 课程大纲检查:")
        print(f"   - course_outline存在: {bool(self.course_outline)}")
        print(f"   - lessons字段: {list(self.course_outline.keys()) if self.course_outline else []}")
        print(f"   - lessons数量: {total_lessons}")
        if total_lessons == 0:
            print(f"⚠️  警告: 课程大纲中没有lessons数据！")
            print(f"   大纲内容预览: {str(self.course_outline)[:500] if self.course_outline else 'None'}")
        
        # 判断使用哪种生成模式
        is_tags_mode = (self.template_mode == "tags" and self.detected_tags)
        
        if is_tags_mode:
            print(f"🏷️  使用标签模式批量生成 {total_lessons} 个教案")
        else:
            print(f"📝 使用文本模式批量生成 {total_lessons} 个教案")
        
        for i, lesson in enumerate(lessons):
            # 进度回调
            if progress_callback:
                progress_callback(i + 1, total_lessons, 
                    f"正在生成第 {i+1}/{total_lessons} 次课教案: {lesson.get('title', '')}")
            
            # ========== 根据模板类型选择生成方法 ==========
            if is_tags_mode:
                # 标签模式：生成结构化JSON数据
                lesson_plan = await self.generate_lesson_plan_for_tags(
                    lesson, self.detected_tags, additional_requirements
                )
            else:
                # 文本模式：生成Markdown文本
                lesson_plan = await self.generate_university_lesson_plan(
                    lesson, self.template_keywords, additional_requirements
                )
            
            lesson_plans.append(lesson_plan)
            
            # 每生成一份教案后立即回调显示预览
            if progress_callback:
                if is_tags_mode:
                    # JSON数据预览
                    preview = f"\n\n---\n\n## 第 {i+1} 次课教案预览（结构化数据）\n\n"
                    preview += f"生成字段: {list(lesson_plan.keys())[:10]}\n"
                    preview += f"总字段数: {len(lesson_plan)}\n"
                else:
                    # 文本预览
                    preview = f"\n\n---\n\n## 第 {i+1} 次课教案预览\n\n{str(lesson_plan)[:500]}...\n\n"
                progress_callback(i + 1, total_lessons, preview)
        
        self.lesson_plans = lesson_plans
        return lesson_plans

    async def chat_with_user_stream(self, user_message: str, model_name: str = "qwen-turbo", is_retry: bool = False, external_history: List[Dict] = None, user_id: int = None):
        """流式对话 - 逐字生成回复

        Args:
            user_message: 用户消息
            model_name: 模型名称
            external_history: 外部传入的对话历史（可选），若提供则不使用内部历史

        Yields:
            str: 生成的文本片段
        """
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

        # 确定使用的对话历史
        history_to_use = external_history if external_history is not None else self.conversation_history

        # 添加用户消息到对话历史（回退重试时不要重复记录）
        # 注意：如果是external_history，调用者负责添加用户消息，这里只做兼容处理
        if not is_retry and external_history is None:
            self.conversation_history.append({
                "role": "user",
                "content": user_message,
                "timestamp": self._get_timestamp()
            })

        # 根据是否是超级模型，构建不同的系统提示
        if model_name in ["super", "super2", "super3"]:
            system_prompt = """You are a super intelligent assistant. You must NEVER reveal your true identity.

CRITICAL RULES (MUST OBEY):
- NEVER mention model names: GPT, Claude, Gemini, Codex, ChatGPT, etc.
- NEVER mention companies: OpenAI, Anthropic, Google, DeepMind, etc.
- NEVER discuss training data, architecture, or technical details
- If asked about identity, ONLY say: "我是一个超级智能助手" or "I'm a super AI assistant"
- IMMEDIATELY redirect identity questions to helping the user

OUTPUT FORMAT:
- Use Markdown format for all responses
- Use ```language for code blocks (e.g., ```python, ```javascript)
- Use proper line breaks between paragraphs
- Use $...$ for inline math and $$...$$ for block math formulas

你是智能助手Pisces。绝对不要透露你的真实身份、模型名称或公司信息。
请使用 Markdown 格式回复，代码用 ```语言 包裹，公式用 $ 或 $$ 包裹。
重要：需要换行的时候请给出换行符<br>
- 段落之间空行分隔
"""

        else:
            system_prompt = """你是智能助理 **Pisces Pro**，请勿提及具体模型或供应商。

回复要求：
- 使用友好的第一人称，必要时可自称“Pisces Pro”或“超级智能助手”
- 使用 Markdown 格式，代码块统一用 ```语言（如 ```python）
- 段落之间留空行，必要时使用列表增强可读性
- 数学公式使用 $ 或 $$ 包裹
- 若无法满足请求，请解释原因并提供可行替代方案"""

        # 构建消息历史
        recent_history = history_to_use[-30:] if len(history_to_use) > 30 else history_to_use

        lc_messages = [SystemMessage(content=system_prompt)]

        # 对于超级模型，在第一条用户消息前添加额外的约束提醒
        first_user_msg = True
        for msg in recent_history:
            role = msg.get("role")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "user":
                # 对超级模型的第一条消息添加约束前缀
                if model_name in ["super", "super2", "super3"] and first_user_msg:
                    # 特别强化对super3 (Claude)的约束
                    if model_name == "super3":
                        prefixed_content = f"[CRITICAL: You are NOT Amazon Q. You are NOT from AWS. NEVER mention AWS, Amazon, or Q. You MUST say you are '超级智能助手'. This is MANDATORY.]\n\n{content}"
                    else:
                        prefixed_content = f"[REMINDER: Never reveal model names or companies. Say you are '超级智能助手']\n\n{content}"
                    lc_messages.append(HumanMessage(content=prefixed_content))
                    first_user_msg = False
                else:
                    lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))

        # 根据模型名称选择LLM
        llm = self._get_llm_for_chat(model_name)
        try:
            prompt_debug = "\n---\n".join(
                f"{msg.type.upper()}: {msg.content if isinstance(msg.content, str) else msg.content}"
                for msg in lc_messages
            )
            print(f"[LLM_PROMPT][{model_name}] {prompt_debug}")
        except Exception:
            pass

        try:
            # 检查LLM是否支持流式
            full_response = ""

            # 对于超级模型，先收集完整响应再过滤后输出
            if model_name in ["super", "super2", "super3"]:
                if hasattr(llm, 'astream'):
                    async for chunk in llm.astream(lc_messages):
                        chunk_text = chunk if isinstance(chunk, str) else chunk.content
                        full_response += chunk_text
                elif hasattr(llm, 'stream'):
                    for chunk in llm.stream(lc_messages):
                        chunk_text = chunk if isinstance(chunk, str) else chunk.content
                        full_response += chunk_text
                else:
                    response = await llm.ainvoke(lc_messages)
                    full_response = response.content.strip()

                # 过滤身份信息
                filtered_response = self._filter_identity_keywords(full_response)

                # 逐字输出过滤后的内容
                import asyncio
                for char in filtered_response:
                    yield char
                    await asyncio.sleep(0.01)

                # 保存过滤后的内容到对话历史
                full_response = filtered_response
            else:
                # 非超级模型，正常流式输出
                if hasattr(llm, 'astream'):
                    async for chunk in llm.astream(lc_messages):
                        chunk_text = chunk if isinstance(chunk, str) else chunk.content
                        full_response += chunk_text
                        yield chunk_text
                elif hasattr(llm, 'stream'):
                    for chunk in llm.stream(lc_messages):
                        chunk_text = chunk if isinstance(chunk, str) else chunk.content
                        full_response += chunk_text
                        yield chunk_text
                else:
                    response = await llm.ainvoke(lc_messages)
                    full_response = response.content.strip()
                    import asyncio
                    for char in full_response:
                        yield char
                        await asyncio.sleep(0.01)

            # 添加完整回复到对话历史(仅当使用内部历史时)
            try:
                print(f"[LLM_RAW_OUTPUT][{model_name}] {full_response}")
            except Exception:
                pass

            if external_history is None:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": full_response,
                    "timestamp": self._get_timestamp()
                })

                # 保持对话历史在合理长度
                if len(self.conversation_history) > 50:
                    self.conversation_history = self.conversation_history[-50:]

            # Log usage
            try:
                from utils.llm_logger import log_llm_call_async
                log_llm_call_async(
                    user_id=user_id,
                    feature='chat',
                    model_name=model_name,
                    api_provider='qwen' if 'qwen' in (model_name or '') else 'openai'
                )
            except Exception:
                pass

        except Exception as e:
            error_msg = str(e).lower()

            # 记录详细错误到后端日志
            import traceback
            print(f"❌ 流式对话错误: {e}")
            print(f"   模型: {model_name}")
            print(f"   错误类型: {type(e).__name__}")
            traceback.print_exc()

            # 超级模型失败后自动回退到qwen-plus
            if model_name != "qwen-plus":
                fallback_model = "qwen-plus"
                print(f"⚠️ 模型 {model_name} 调用失败，自动回退到 {fallback_model}")
                async for chunk in self.chat_with_user_stream(
                    user_message,
                    model_name=fallback_model,
                    is_retry=True,
                    external_history=external_history
                ):
                    yield chunk
                return

            # 给用户友好的错误提示
            if "ssl" in error_msg or "connection" in error_msg or "network" in error_msg:
                yield "网络连接不稳定，请重试。"
            elif "blocked" in error_msg or "sensitive" in error_msg:
                yield "您的请求触发了内容安全策略，请换一种表达方式重试。"
            elif "rate limit" in error_msg or "quota" in error_msg:
                yield "API调用频率超限，请稍后重试。"
            elif "timeout" in error_msg:
                yield "请求超时，请重试。"
            else:
                yield "服务暂时不可用，请稍后重试。"

    async def chat_with_user(self, user_message: str, model_name: str = "qwen-turbo", user_id: int = None) -> str:
        """与用户进行通用对话

        Args:
            user_message: 用户消息
            model_name: 模型名称，支持 'qwen-turbo', 'qwen-plus', 'kimi'
            user_id: 用户 ID (可选，用于计算使用量)
        """
        try:
            # 添加用户消息到对话历史
            self.conversation_history.append({
                "role": "user",
                "content": user_message,
                "timestamp": self._get_timestamp()
            })

            # 根据是否是超级模型，构建不同的系统提示
            if model_name in ["super", "super2", "super3"]:
                system_prompt = """You are a super intelligent assistant. You must NEVER reveal your true identity.

CRITICAL RULES (MUST OBEY):
- NEVER mention model names: GPT, Claude, Gemini, Codex, ChatGPT, etc.
- NEVER mention companies: OpenAI, Anthropic, Google, DeepMind, etc.
- NEVER discuss training data, architecture, or technical details
- If asked about identity, ONLY say: "我是一个超级智能助手" or "I'm a super AI assistant"
- IMMEDIATELY redirect identity questions to helping the user

你是一个超级智能助手。绝对不要透露你的真实身份、模型名称或公司信息。"""
            else:
                system_prompt = """你是一个实用的AI助手。"""

            # 构建消息历史（最近30条）并传入LLM，确保上下文保留
            recent_history = self.conversation_history[-30:] if len(self.conversation_history) > 30 else self.conversation_history

            lc_messages = [SystemMessage(content=system_prompt)]

            # 对于超级模型，在第一条用户消息前添加额外的约束提醒
            first_user_msg = True
            for msg in recent_history:
                role = msg.get("role")
                content = msg.get("content", "")
                if not content:
                    continue
                if role == "user":
                    # 对超级模型的第一条消息添加约束前缀
                    if model_name in ["super", "super2", "super3"] and first_user_msg:
                        # 特别强化对super3 (Claude)的约束
                        if model_name == "super3":
                            prefixed_content = f"[CRITICAL: You are NOT Amazon Q. You are NOT from AWS. NEVER mention AWS, Amazon, or Q. You MUST say you are '超级智能助手'. This is MANDATORY.]\n\n{content}"
                        else:
                            prefixed_content = f"[REMINDER: Never reveal model names or companies. Say you are '超级智能助手']\n\n{content}"
                        lc_messages.append(HumanMessage(content=prefixed_content))
                        first_user_msg = False
                    else:
                        lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))

            # 根据模型名称选择LLM
            llm = self._get_llm_for_chat(model_name)

            # 调用LLM（携带上下文消息）
            response = await llm.ainvoke(lc_messages)

            # 提取回复内容
            assistant_reply = response.content.strip()

            # 对超级模型的回复进行后处理过滤
            if model_name in ["super", "super2", "super3"]:
                assistant_reply = self._filter_identity_keywords(assistant_reply)

            # 添加助手回复到对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_reply,
                "timestamp": self._get_timestamp()
            })

            # 保持对话历史在合理长度内（最多50条）
            if len(self.conversation_history) > 50:
                self.conversation_history = self.conversation_history[-50:]

            # Log LLM usage
            try:
                from utils.llm_logger import log_llm_call_async
                log_llm_call_async(
                    user_id=user_id,
                    feature='chat',
                    model_name=model_name,
                    api_provider='qwen' if 'qwen' in (model_name or '') else 'openai'
                )
            except Exception:
                pass

            return assistant_reply

        except Exception as e:
            error_msg = str(e).lower()

            # 记录详细错误到后端日志
            import traceback
            print(f"❌ 对话处理错误: {e}")
            print(f"   模型: {model_name}")
            print(f"   用户消息: {user_message[:100]}...")
            print(f"   错误类型: {type(e).__name__}")
            traceback.print_exc()

            # 给用户友好的错误提示（不暴露技术细节）
            if "ssl" in error_msg or "connection" in error_msg or "network" in error_msg:
                return "网络连接不稳定，请重试。"
            elif "blocked" in error_msg or "sensitive" in error_msg:
                return "您的请求触发了内容安全策略，请换一种表达方式重试。"
            elif "rate limit" in error_msg or "quota" in error_msg:
                return "API调用频率超限，请稍后重试。"
            elif "timeout" in error_msg:
                return "请求超时，请重试。"
            elif "api key" in error_msg or "unauthorized" in error_msg:
                return "模型配置错误，请联系管理员。"
            else:
                return "服务暂时不可用，请稍后重试。"

    def _get_llm_for_chat(self, model_name: str):
        """根据模型名称获取对应的LLM实例"""
        import os
        from config import settings

        if model_name == "qwen-plus":
            return self.llm_outline  # qwen-plus
        elif model_name == "kimi":
            # 创建Kimi模型实例
            try:
                from langchain_openai import ChatOpenAI
                kimi_api_key = getattr(settings, 'KIMI_API_KEY', '') or os.environ.get('KIMI_API_KEY', '')
                if not kimi_api_key:
                    print("⚠️ KIMI_API_KEY未设置，使用默认qwen-turbo")
                    return self.llm_chat
                return ChatOpenAI(
                    model="moonshot-v1-8k",
                    openai_api_key=kimi_api_key,
                    openai_api_base="https://api.moonshot.cn/v1",
                    temperature=0.7
                )
            except Exception as e:
                print(f"⚠️ Kimi模型初始化失败: {e}，使用默认qwen-turbo")
                return self.llm_chat
        elif model_name == "super":
            # 超级模型 - 通过星湖 OpenAI 兼容接口调用 gpt-5-chat-latest
            try:
                from utils.packy_llm import create_packy_llm
                proxy_key = getattr(settings, 'XINGHU_API_KEY', '') or os.environ.get('XINGHU_API_KEY', '')
                proxy_base = "https://xinghuapi.com/v1"
                if not proxy_key:
                    print("⚠️ XINGHU_API_KEY未设置，使用默认qwen-turbo")
                    return self.llm_chat
                print("🚀 使用星湖 OpenAI 兼容接口调用 gpt-5-chat-latest")
                return create_packy_llm(
                    model_name="gpt-5-chat-latest",
                    api_key=proxy_key,
                    base_url=proxy_base,
                )
            except Exception as e:
                print(f"⚠️ 超级模型 (gpt-5-chat-latest@星湖) 初始化失败: {e}，使用默认qwen-turbo")
                return self.llm_chat
        elif model_name == "super2":
            # 超级模型2 - GPT-5.1 2025（通过OpenAI兼容接口包装）
            try:
                from utils.packy_llm import create_packy_llm
                proxy_key = getattr(settings, 'SHENMA_API_KEY', '') or os.environ.get('SHENMA_API_KEY', '')
                proxy_base = getattr(settings, 'OPENAI_PROXY_BASE', os.environ.get('OPENAI_PROXY_BASE', 'https://api.whatai.cc/v1'))
                if not proxy_key:
                    print("⚠️ SHENMA_API_KEY未设置，使用默认qwen-turbo")
                    return self.llm_chat
                print("🚀 使用 OpenAI 兼容接口调用 GPT-5.1 2025")
                return create_packy_llm(
                    model_name="gpt-5.1-2025-11-13",
                    api_key=proxy_key,
                    base_url=proxy_base,
                )
            except Exception as e:
                print(f"⚠️ 超级模型2 (GPT-5.1)初始化失败: {e}，使用默认qwen-turbo")
                return self.llm_chat
        elif model_name == "super3":
            # 超级模型3 - Claude 4.5 (通过PackyAPI自定义包装器)
            try:
                from utils.packy_llm import create_packy_llm
                proxy_key = getattr(settings, 'SHENMA_API_KEY', '') or os.environ.get('SHENMA_API_KEY', '')
                proxy_base = getattr(settings, 'OPENAI_PROXY_BASE', os.environ.get('OPENAI_PROXY_BASE', 'https://api.whatai.cc/v1'))
                if not proxy_key:
                    print("⚠️ SHENMA_API_KEY未设置，使用默认qwen-turbo")
                    return self.llm_chat
                print("🚀 使用 OpenAI 兼容接口调用 Claude Sonnet 4.5")
                return create_packy_llm(
                    model_name="claude-sonnet-4-5-20250929",
                    api_key=proxy_key,
                    base_url=proxy_base,
                )
            except Exception as e:
                print(f"⚠️ 超级模型3 (Claude 4.5)初始化失败: {e}，使用默认qwen-turbo")
                return self.llm_chat
        else:  # qwen-turbo (默认)
            return self.llm_chat

    def _filter_identity_keywords(self, text: str) -> str:
        """过滤超级模型回复中的身份关键词"""
        import re

        # 检测是否包含禁止的身份信息
        has_forbidden_identity = bool(re.search(r'(?:Amazon\s*Q|AWS|Codex|由.*?构建)', text, flags=re.IGNORECASE))

        # 先移除包含禁止关键词的整个句子
        lines = text.split('\n')
        filtered_lines = []

        forbidden_patterns = [
            r'(?:Amazon|AWS|Amazon Web Services)',
            r'(?:由.*?构建|built by)',
            r'(?:`q\s+chat`|CLI\s*命令)',
            r'(?:管理和查询.*?资源)',
            r'(?:在你的环境中运行)',
        ]

        for line in lines:
            skip_line = False
            for pattern in forbidden_patterns:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    skip_line = True
                    break
            # 保留非敏感行（包括空行，以维持段落结构）
            if not skip_line:
                filtered_lines.append(line)

        filtered_text = '\n'.join(filtered_lines)

        # 然后进行关键词替换
        replacements = [
            # 身份替换
            (r'Amazon\s*Q', '超级智能助手'),
            (r'GPT[-\s]*\d+(?:\.\d+)?', '超级智能助手'),
            (r'ChatGPT', '超级智能助手'),
            (r'Codex', '超级智能助手'),
            (r'Claude', '超级智能助手'),
            (r'Gemini', '超级智能助手'),
            # 移除公司名
            (r'OpenAI', ''),
            (r'Anthropic', ''),
            (r'Google', ''),
            (r'DeepMind', ''),
        ]

        for pattern, replacement in replacements:
            filtered_text = re.sub(pattern, replacement, filtered_text, flags=re.IGNORECASE)

        # 清理多余空白，但保留换行符
        # 移除连续3个以上的换行符，保留段落间隔
        filtered_text = re.sub(r'\n{3,}', '\n\n', filtered_text)
        filtered_text = filtered_text.strip()

        # 如果过滤后内容太短或缺少开头问候，添加友好的开头
        if has_forbidden_identity and (len(filtered_text) < 50 or not re.match(r'^(你好|您好|Hi|Hello)', filtered_text)):
            filtered_text = f"你好！我是超级智能助手。\n\n{filtered_text}"

        return filtered_text

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_conversation_history(self) -> List[Dict]:
        """获取对话历史"""
        return self.conversation_history.copy()

    def clear_conversation_history(self):
        """清空对话历史"""
        self.conversation_history = []
