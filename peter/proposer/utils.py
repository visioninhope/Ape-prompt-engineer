from dataclasses import dataclass, asdict
import json
import re
from typing import Any, Dict, List

from peter.prompt.prompt_base import Prompt
from peter.types import DataItem


def extract_prompt(text: str):
    match = re.search(r"```prompt(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        raise ValueError("No prompt found")


# NOTE: Use dataclass instead of pydantic BaseModel because `Prompt` isn't a pydanitc model
@dataclass
class HistoryItem:
    prompt: Prompt
    score: float


@dataclass
class AggregatedHistoryItem:
    total_score: float
    count: int


def create_history_string(prompt: Prompt, trial_logs, top_n: int):
    instruction_aggregate: Dict[str, AggregatedHistoryItem] = {}
    instruction_history: List[HistoryItem] = []

    # Load trial programs
    for trial_num in trial_logs:
        trial = trial_logs[trial_num]
        if "prompt_path" in trial:
            trial_prompt = prompt.deepcopy()
            # TODO: NOTE: look into this
            trial_prompt.load(trial["prompt_path"])
            instruction_history.append(
                HistoryItem(
                    prompt=trial_prompt,
                    score=trial["score"],
                )
            )

    # Aggregate scores for each instruction
    for history_item in instruction_history:
        instruction: str = json.dumps(history_item.prompt.messages)
        score = history_item.score

        if instruction in instruction_aggregate:
            instruction_aggregate[instruction].total_score += score
            instruction_aggregate[instruction].count += 1
        else:
            instruction_aggregate[instruction] = AggregatedHistoryItem(
                total_score=score,
                count=1,
            )

    # Calculate average score for each instruction and prepare for sorting
    predictor_history = []
    for instruction, data in instruction_aggregate.items():
        average_score = data.total_score / data.count
        predictor_history.append((instruction, average_score))

    # Deduplicate and sort by average score, then select top N
    seen_instructions = set()
    unique_predictor_history = []
    for instruction, score in predictor_history:
        if instruction not in seen_instructions:
            seen_instructions.add(instruction)
            unique_predictor_history.append((instruction, score))

    top_instructions = sorted(
        unique_predictor_history, key=lambda x: x[1], reverse=True
    )[:top_n]
    top_instructions.reverse()

    # Create formatted history string
    predictor_history_string = ""
    for instruction, score in top_instructions:
        predictor_history_string += instruction + f" | Score: {score}\n\n"

    return predictor_history_string
