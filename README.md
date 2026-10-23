# 直播间场景 Skill V3.3.0（开发版）

全棉时代 × 奈丝公主｜团队可复用的AI直播间背景工作流。

## 5分钟使用流程
**需求确认卡 → 品牌Logo/色卡实际加载检查 → 有图等待上传/无图自主提案 → 人工确认方向 → 完整提示词 + 固定3张独立3:4图 → A/B/C选图与多项反馈 → 锁定原图并每轮固定3张精修 → 9:16安全区检查 → 定稿。**

### 关键约束
- 没有用户确认方向不能生图；有参考图时不能擅用别的项目图片。
- 不论第一轮还是后续精修，**每轮固定3张独立图**。精修基于同一真实锁定图；不能文字重生冒充编辑。
- **每次出图后**必须继续提供A/B/C、都不满意、历史版、多项修改、自由反馈；不可只留下图片。没有交互按钮用编号文字。
- 全棉时代标准色 **#00AC97 / RGB(0,172,151)**；精准要求请后期校色。官方Logo请使用真实源文件合成，AI绘制不能保证不变形。
- 默认3:4远景大空间，兼顾9:16裁切；居中裁9:16左右各裁去母图宽的**12.5%**。
- GitHub更新不会让豆包/ChatGPT已安装实例自动同步。

## 文件导览
- [核心Skill规则](SKILL.md)
- [画面锁定协议](references/image-lock.md)
- [标准反馈面板](references/interaction.md)
- [品牌Logo与色卡规范](references/brand-guidelines.md)
- [9:16安全区设计标准](references/safe-area.md)
- [每轮输出检查清单](references/output-checklist.md)
- [团队验收用例](tests/acceptance.md)
- [同事5分钟文字教程](docs/同事5分钟上手教程.md)
- [版本历史](CHANGELOG.md)\n- [Skill与程序控制的能力边界](references/runtime-boundaries.md)\n- [可运行的本地工作台](controller/README.md)

## 运行时能力边界\nSkill文字不能强制显示交互控件或执行原图编辑。V3.3提供本地持久化工作台；需要配置图像生成/编辑提供方后才能真实出图。当前仓库不包含该平台适配器或凭据。\n\n## 官方品牌素材
- 全棉时代：[绿色Logo](assets/logos/三层LOGO-绿.png) / [白色Logo](assets/logos/三层LOGO-白.png)
- 奈丝公主：[标准Logo](assets/logos/LOGO.png)
- [全棉时代标准绿参考色卡](assets/colors/purcotton-green.svg)

## 权限与安装说明
仓库可能公开，请自行评估公司商标素材和内部资料能否对外展示；公开并不等于授权第三方再利用。安装到豆包、ChatGPT等平台时须同时导入相关图片文件及规则，不能只复制README。
