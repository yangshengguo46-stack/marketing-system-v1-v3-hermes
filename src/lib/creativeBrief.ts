export function encodeCreativeBrief(brief: CreativeBrief) {
  return encodeURIComponent(JSON.stringify(brief))
}

export function decodeCreativeBrief(payload: string): CreativeBrief | null {
  try {
    const parsed = JSON.parse(decodeURIComponent(payload)) as CreativeBrief
    if (!parsed || typeof parsed.title !== 'string') return null
    return parsed
  } catch {
    return null
  }
}

export function creativeBriefToPrompt(brief: CreativeBrief) {
  const evidence = (brief.evidence || [])
    .filter((item) => item.label || item.value)
    .map((item) => `- ${item.label}：${item.value}`)
    .join('\n')
  const angles = (brief.angles || [])
    .filter(Boolean)
    .map((angle, index) => `${index + 1}. ${angle}`)
    .join('\n')
  return [
    `请以这条选题线索作为起点，和我一起打磨成可发布内容：${brief.title}`,
    brief.source_label ? `来源：${brief.source_label}` : '',
    brief.heat ? `热度/等级：${brief.heat}` : '',
    brief.rank ? `排名：${brief.rank}` : '',
    brief.target_audience ? `目标受众：${brief.target_audience}` : '',
    evidence ? `已有证据：\n${evidence}` : '',
    angles ? `候选角度：\n${angles}` : '',
    '',
    brief.recommended_action || '请先判断它是否适合当前账号，再给我 3 个更强的切入角度、标题、脚本结构和需要补充的证据。不要编造未验证数据。',
    '',
    '回复格式要求：',
    '1. 不要把工具名、数据库字段、完整证据流水账原样贴出来。',
    '2. 只输出四块：一句话结论 / 为什么 / 3 个可做角度 / 需要我补充什么。',
    '3. 每块最多 3 条，语言像给真人创作者沟通，不要写成报告。',
    '4. 如果证据不足，先明确说“不建议直接做”，再给替代路径。',
    '5. 如果已经足够形成一版草稿，请调用 marketing_draft_content_create 保存为内容资产草稿；如果还没到成稿程度，先不要保存。',
  ].filter(Boolean).join('\n')
}
