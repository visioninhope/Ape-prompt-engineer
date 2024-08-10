import json
from typing import Dict, List, Optional, Tuple, Union

import optuna
import sqlalchemy
from pydantic import ConfigDict
from ape.optimizer.mipro.mipro_base import MIPROBase
from ape.optimizer.mipro.mipro_proposer import MIPROProposer
from ape.optimizer.utils import reformat_prompt_xml_style
from ape.prompt.prompt_base import Prompt
from ape.types import Dataset
from ape.types.dataset_item import DatasetItem


class MIPROWithHIL(MIPROBase):
    instruction_candidates: List[Prompt] = []
    fewshot_candidates: List[DatasetItem] = []
    storage: optuna.storages.RDBStorage = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, db_url: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_storage(db_url)

    def setup_storage(self, db_url: str):
        engine = sqlalchemy.create_engine(db_url)

        with engine.connect() as connection:
            connection.execute(sqlalchemy.text("CREATE SCHEMA IF NOT EXISTS optuna;"))
            connection.commit()

        # Create Optuna RDB storage with schema specified
        storage_url = f"{db_url}?options=-c%20search_path=optuna"
        self.storage = optuna.storages.RDBStorage(
            url=storage_url,
            engine_kwargs={
                "pool_size": 20,
                "max_overflow": 0,
                "connect_args": {"options": "-c search_path=optuna"},
            },
        )

    async def create_or_load_study(
        self,
        study_name: str,
        trainset: Optional[Dataset] = None,
        task_description: Optional[str] = None,
        prompt_desc: Optional[str] = None,
        inputs_desc: Optional[Dict[str, str]] = None,
        outputs_desc: Optional[Dict[str, str]] = None,
        base_prompt: Optional[Prompt] = None,
    ) -> Tuple[optuna.Study, bool]:
        if self.storage is None:
            raise ValueError("Storage is not set up.")

        study = optuna.create_study(
            study_name=study_name,
            storage=self.storage,
            load_if_exists=True,
            direction="maximize",
            sampler=optuna.samplers.TPESampler(multivariate=True),
        )

        is_new_study = len(study.trials) == 0

        if is_new_study:
            if not trainset:
                raise ValueError("Trainset is required for a new study.")
            if not task_description:
                raise ValueError("Task description is required for a new study.")
            if base_prompt:
                base_prompt = await reformat_prompt_xml_style(base_prompt)
            proposer = MIPROProposer(**self.model_dump())
            self.instruction_candidates = await proposer.generate_candidates(
                prompt=base_prompt,
                trainset=trainset,
                task_description=task_description,
                prompt_desc=prompt_desc,
                inputs_desc=inputs_desc,
                outputs_desc=outputs_desc,
            )
            study.set_user_attr(
                "prompt_candidates",
                json.dumps([p.dump() for p in self.instruction_candidates]),
            )
            study.set_user_attr(
                "fewshot_candidates",
                json.dumps(
                    [
                        d.model_dump() if isinstance(d, DatasetItem) else d
                        for d in trainset
                    ]
                ),
            )
        else:
            prompt_candidates_json = study.user_attrs["prompt_candidates"]
            fewshot_candidates_json = study.user_attrs["fewshot_candidates"]
            self.instruction_candidates = [
                Prompt.load(p) for p in json.loads(prompt_candidates_json)
            ]
            self.fewshot_candidates = [
                DatasetItem(**d) for d in json.loads(fewshot_candidates_json)
            ]

        return study, is_new_study

    def suggest_next_prompt(self, study: optuna.Study) -> Tuple[optuna.Trial, Prompt]:
        trial = study.ask()
        instruction_idx = trial.suggest_categorical(
            "instruction",
            range(len(self.instruction_candidates)),
        )
        prompt = self.instruction_candidates[instruction_idx]
        fewshot_idx = trial.suggest_categorical(
            "fewshot", range(len(self.fewshot_candidates))
        )
        prompt.fewshot = self.fewshot_candidates[fewshot_idx]

        return trial, prompt

    def complete_trial(
        self, study: optuna.Study, trial: Union[optuna.Trial, int], score: float
    ):
        study.tell(trial, score)

    async def get_best_prompt(self, study: optuna.Study) -> Prompt:
        best_trial = study.best_trial
        instruction_idx = best_trial.params["instruction"]
        fewshot_idx = best_trial.params["fewshot"]
        prompt = self.instruction_candidates[instruction_idx]
        prompt.fewshot = self.fewshot_candidates[fewshot_idx]

        return prompt
