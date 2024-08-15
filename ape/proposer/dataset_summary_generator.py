import asyncio
import json
from typing import List, Dict, Any
from functools import partial

from ape.prompt.prompt_base import Prompt
from ape.types import Dataset
from ape.types.dataset_item import DatasetItem
from ape.types.response_format import ResponseFormat, ResponseFormatType


async def process_batch(
    trainset: Dataset,
    batch_start: int,
    batch_end: int,
    prompt_model: str,
) -> str:
    descriptor = Prompt.from_filename("dataset-descriptor")
    descriptor.response_format = ResponseFormat(type=ResponseFormatType.XML)
    descriptor.model = prompt_model
    trainset = [
        item.model_dump() if isinstance(item, DatasetItem) else item
        for item in trainset[batch_start:batch_end]
    ]
    output = await descriptor(
        lm_config=dict(temperature=1.0),
        examples=", ".join([sorted(item.keys()).__repr__() for item in trainset]),
    )
    return output["observations"]


async def create_dataset_summary(
    trainset: Dataset,
    view_data_batch_size: int,
    prompt_model: str,
    log_file=None,
):
    upper_lim = min(len(trainset), view_data_batch_size)

    # Initial batch processing
    observations = await process_batch(trainset, 0, upper_lim, prompt_model)

    # if log_file:
    #     log_file.write("PRODUCING DATASET SUMMARY\n")
    return observations
    # max_calls = 10
    # batch_starts = range(view_data_batch_size, len(trainset), view_data_batch_size)
    # descriptor_with_prior = Prompt.from_filename(
    #     "dataset-descriptor-with-prior-observations"
    # )

    # async def process_subsequent_batch(b: int):
    #     nonlocal observations
    #     upper_lim = min(len(trainset), b + view_data_batch_size)
    #     descriptor_with_prior.model = prompt_model
    #     output = await descriptor_with_prior(
    #         lm_config=dict(temperature=1.0),
    #         prior_observations=observations,
    #         examples=", ".join(
    #             [sorted(item.keys()).__repr__() for item in trainset[b:upper_lim]]
    #         ),
    #     )
    #     if isinstance(output, str):
    #         return output
    #     return output.get("observations", json.dumps(output))

    # # Process subsequent batches in parallel
    # tasks = [process_subsequent_batch(b) for b in batch_starts[:max_calls]]
    # batch_results = await asyncio.gather(*tasks)

    # for result in batch_results:
    #     if len(result) >= 8 and result[:8].upper() == "COMPLETE":
    #         continue
    #     observations += result

    #     if log_file:
    #         log_file.write(f"observations {observations}\n")

    # # Summarize observations
    # obs_summarizer = Prompt.from_filename("observation-summarizer")
    # obs_summarizer.model = prompt_model
    # output = await obs_summarizer(
    #     lm_config=dict(temperature=1.0), observations=observations
    # )
    # summary = output["summary"]
    # print(f"summary: {summary}")
    # if log_file:
    #     log_file.write(f"summary: {summary}\n")

    # return summary
