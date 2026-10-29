import React, { ChangeEvent } from 'react';

interface ToneSelectorProps {
  tone: string;
  onToneChange: (event: ChangeEvent<HTMLSelectElement>) => void;
}
export default function ToneSelector({ tone, onToneChange }: ToneSelectorProps) {
  return (
    <div className="form-group">
      <label htmlFor="tone" className="agent_question">写作风格 </label>
      <select 
        name="tone" 
        id="tone" 
        value={tone} 
        onChange={onToneChange} 
        className="form-control-static"
        required
      >
        <option value="Objective">客观 · 中立呈现事实与研究发现</option>
        <option value="Formal">正式 · 遵循学术规范，语言与结构严谨</option>
        <option value="Analytical">分析 · 深入分析数据与理论</option>
        <option value="Persuasive">论证 · 以充分论据阐明观点</option>
        <option value="Informative">资讯 · 清晰、全面地介绍主题</option>
        <option value="Explanatory">解释 · 说明复杂概念与过程</option>
        <option value="Descriptive">描述 · 细致呈现现象、实验或案例</option>
        <option value="Critical">批判 · 评估研究及结论的有效性与相关性</option>
        <option value="Comparative">比较 · 对照理论、数据或方法的异同</option>
        <option value="Speculative">探索 · 讨论假设、潜在影响与未来方向</option>
        <option value="Reflective">反思 · 回顾研究过程与经验</option>
        <option value="Narrative">叙述 · 通过故事说明研究发现或方法</option>
        <option value="Humorous">幽默 · 轻松生动，易于理解</option>
        <option value="Optimistic">积极 · 关注正面发现与潜在收益</option>
        <option value="Pessimistic">审慎 · 关注局限、挑战与不利结果</option>
        <option value="Simple">简明 · 用简单词汇清楚说明</option>
        <option value="Casual">轻松 · 自然口语化，便于日常阅读</option>
      </select>
    </div>
  );
}