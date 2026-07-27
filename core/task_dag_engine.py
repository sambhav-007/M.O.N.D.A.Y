"""
M.O.N.D.A.Y. — Dynamic Multi-Step Task DAG Execution Engine
============================================================
Parses complex user requests into a Directed Acyclic Graph (DAG) of multi-agent execution steps.
Passes output from Step N as contextual input to Step N+1.
"""

from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional
from pathlib import Path


class TaskNode:
    """Represents a single executable node in the Multi-Agent Task DAG."""

    def __init__(self, step_id: int, agent_type: str, action: str, prompt: str, target: str = "") -> None:
        self.step_id = step_id
        self.agent_type = agent_type
        self.action = action
        self.prompt = prompt
        self.target = target
        self.result: Optional[Dict[str, Any]] = None
        self.completed = False


class TaskDAGEngine:
    """Dynamic Multi-Step Agent Workflow & DAG Orchestrator."""

    def __init__(self, planner_ref: Any) -> None:
        self.planner = planner_ref

    def is_multi_step_goal(self, command: str) -> bool:
        """Determines if user prompt contains a compound multi-step request."""
        cmd_lower = command.lower()
        delimiters = [" and then ", " then ", " and save ", " and draft ", " and email ", " and summarize ", ", then "]
        return any(d in cmd_lower for d in delimiters) and len(command.split()) >= 6

    def parse_command_to_dag(self, command: str) -> List[TaskNode]:
        """Parses multi-step prompt into an ordered list of TaskNodes."""
        # Split command into logical sub-tasks
        sub_prompts = re.split(r'\s+(?:and then|then|and save|and draft|and email|and summarize|, then)\s+', command, flags=re.IGNORECASE)
        nodes: List[TaskNode] = []

        for idx, sub_p in enumerate(sub_prompts, start=1):
            sub_p = sub_p.strip()
            sub_lower = sub_p.lower()

            if any(k in sub_lower for k in ["search", "google", "research", "find"]):
                agent_type = "browser"
                action = "web_search"
            elif any(k in sub_lower for k in ["summarize", "summary", "digest"]):
                agent_type = "document"
                action = "summarize"
            elif any(k in sub_lower for k in ["save", "write file", "create file", "export"]):
                agent_type = "computer"
                action = "save_file"
            elif any(k in sub_lower for k in ["email", "draft", "message", "send"]):
                agent_type = "comms"
                action = "draft_email"
            else:
                agent_type = "planner"
                action = "process_command"

            nodes.append(TaskNode(step_id=idx, agent_type=agent_type, action=action, prompt=sub_p))

        return nodes

    def execute_dag(self, command: str, user_approved: bool = True) -> Dict[str, Any]:
        """Executes task DAG sequentially, feeding context between steps."""
        nodes = self.parse_command_to_dag(command)
        execution_trace: List[Dict[str, Any]] = []
        accumulated_context = ""

        print(f"🧠 TaskDAGEngine: Executing {len(nodes)}-step workflow for '{command}'...")

        for node in nodes:
            step_prompt = node.prompt
            if accumulated_context:
                step_prompt = f"{step_prompt} Context: {accumulated_context[:300]}"

            if node.agent_type == "browser":
                step_res = self.planner.browser_agent.web_search(node.prompt)
                output_text = str(step_res.get("results", step_res.get("message", "")))
            elif node.agent_type == "document":
                step_res = self.planner.document_agent.summarize_document(accumulated_context or node.prompt)
                output_text = str(step_res.get("summary", step_res.get("message", "")))
            elif node.agent_type == "computer":
                step_res = self.planner.computer_agent.create_file_artifact("task_dag_output.txt", accumulated_context or node.prompt)
                output_text = str(step_res.get("message", ""))
            elif node.agent_type == "comms":
                to_match = re.search(r'to\s+([^\s,]+)', node.prompt, re.IGNORECASE)
                to_email = to_match.group(1) if to_match else "team@monday.ai"
                step_res = self.planner.comms_agent.draft_email(to_email, "Automated Task Summary", accumulated_context or node.prompt)
                output_text = str(step_res.get("message", ""))
            else:
                step_res = self.planner.process_command(node.prompt, user_approved=user_approved)
                output_text = str(step_res.get("execution_result", {}).get("message", ""))

            node.result = step_res
            node.completed = True
            accumulated_context += f" Step {node.step_id} Output: {output_text}"

            execution_trace.append({
                "step": node.step_id,
                "agent": node.agent_type,
                "action": node.action,
                "prompt": node.prompt,
                "output_snippet": output_text[:120]
            })

        summary_msg = f"✓ Dynamic Task DAG Executed Successfully ({len(nodes)} Steps Completed):\n"
        for t in execution_trace:
            summary_msg += f"  • Step {t['step']} [{t['agent'].upper()}]: {t['output_snippet']}\n"

        return {
            "success": True,
            "multi_step_dag": True,
            "steps_count": len(nodes),
            "trace": execution_trace,
            "message": summary_msg.strip()
        }
