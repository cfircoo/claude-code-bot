---
name: perplexity-research
description: Web research using Perplexity API. Use for researching topics, finding docs, current info, comparisons, or questions needing up-to-date web sources. Runs as forked subagent.
user_invocable: true
arg_description: Research query or topic
context: forked
---

<objective>
Delegate web research to a specialized Perplexity subagent that searches the web, synthesizes findings, and returns a structured report with source citations.
</objective>

<instructions>
When this skill is invoked, use the Task tool to spawn a perplexity-research agent:

```
Task tool parameters:
- subagent_type: "perplexity-research"
- description: "Research: [brief topic]"
- prompt: The user's research query with any context needed
```

The subagent will:
1. Check if PERPLEXITY_API_KEY is configured
2. Execute searches via Perplexity API
3. Synthesize findings with source citations
4. Return a structured research report

After receiving the report, summarize key findings for the user.
</instructions>

<usage_examples>
User: "/perplexity-research best practices for Python async"
Action: Spawn perplexity-research agent with query about Python async best practices

User: "/perplexity-research compare FastAPI vs Flask 2024"
Action: Spawn agent to research and compare the two frameworks

User: "Research the latest Claude API features"
Action: Spawn agent to find current Claude API documentation and features
</usage_examples>

<output>
After the subagent returns, present:
1. Brief summary of findings (2-3 sentences)
2. Key points with source links
3. Any limitations or confidence notes from the research
</output>
