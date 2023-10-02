"""Process dataset of simulation results."""

import pathlib
import datetime
from tqdm import tqdm
import pandas as pd
import math
from file_IO_handler import load_json, save_json


def consolidate_jsons_to_mega_json(
    open_folder: pathlib.Path, save_file_path: pathlib.Path
) -> int:
    """Consolidate .json files whose paths follow the glob file_pattern.

    Args:
        open_folder: folder containing .json files.
        save_file_path: path to save consolidated results as .json or .json.gz file.

    Returns:
        Number of files consolidated.
    """
    mega = []
    list_of_data_files = open_folder.glob("**/*.json")  # list .json files in folder

    print(f"Got {len(list_of_data_files)} in folder {open_folder}")

    for data_file in list_of_data_files:
        file_contents = load_json(data_file)
        mega.append(file_contents)

    print("Started saving at: ", str(datetime.datetime.now()))
    save_json(mega, save_file_path)
    print("Started saving at: ", str(datetime.datetime.now()))
    return len(list_of_data_files)


def process_mega_json_for_no_complete_prompt(
    path_to_megajson: pathlib.Path,
    completion_is_last_n_tokens_of_echoed_prompt: int = 1,
    filter_by_prompt_descriptor: None | str = None,
):
    """Process mega .json.gz file from experiment using a no-complete prompt.

    The `consolidate_jsons_to_mega_json` saves the contents of several .json files to a mega .json.gz file.

    The Ultimatum Game simulation and the Garden Path simulation both used no-complete prompts,
    i.e., no completions were generated by the language model.
    Each experiment was run twice to get the probabilities of the two allowed completions:
        "accept" and "reject" for the Ultimatum Game,
        "grammatical" and "ungrammatical" for the Garden Path.

    Given a mega.json.gz, process its contents from a hierarchial structure to a flat dataframe structure.

    Args:
        path_to_megajson: path to the mega .json.gz file with all the results and information for the experiment.
        completion_is_last_n_tokens_of_echoed_prompt: how many tokens from the end of the prompt to get log probs for
            (completions supplied in prompt).
        filter_by_prompt_descriptor: `filter_by_prompt_descriptor` because different prompts (different completions)
            will have different `log_prob_of_last_n_tokens_in_echoed_prompt`

    Returns:
        pandas dataFrame.

    Raises:
        Exception: When using 'no-complete' type prompt, model settings should include echo.
    """
    # Dict to turn into pandas dataframe.
    results = {"index": [], "engine": [], "tokens": [], "probability": []}
    added_prompt_fill_fields_to_results_dict = False

    mega = load_json(filename=path_to_megajson)
    print(f"Found {len(mega)} items in mega .json.gz")

    for res in tqdm(mega):
        # Filter by prompt descriptor and experiment descriptor.
        # Only process results with matching descriptors.
        if (filter_by_prompt_descriptor is not None) and (
            res["input"]["prompt_descriptor"] != filter_by_prompt_descriptor
        ):
            continue

        # Populate field values in results.
        results["index"].append(res["input"]["prompt"]["index"])
        results["engine"].append(res["model"]["engine"])

        # Add prompt fill fields as additional fields in results dict.
        if not added_prompt_fill_fields_to_results_dict:
            for k, v in res["input"]["prompt"]["values"].items():
                results[k] = []
            # Set flag.
            added_prompt_fill_fields_to_results_dict = True

        # Populate prompt fill values in results.
        for k, v in list(res["input"]["prompt"]["values"].items()):
            results[k].append(v)

        # Get log probs for completion supplied in the prompt.
        if not res["model"]["echo"]:
            raise Exception(
                "When using 'no-complete' type prompt, completions should be supplied in prompt so getting probabilites requires echo-ing prompt probabilities."
            )
        # Assume that n = 1 (number of language model responses = 1).
        choice = res["output"]["choices"][0]
        if res["model"]["max_tokens"] == 0:
            # There is no generated text in the output.
            # Prefered way to run 2-choice simulation.
            res["output"]["echo_logprobs"] = choice["logprobs"]
        else:
            # There is generated text in the output (probably by mistake?).
            # This is a problem because completion is counted as tokens from the end of the output.
            # Salvage the run by isolating echo of the prompt from the mistake generation.
            len_input = len(res["input"]["full_input"])
            # Define index to slice with.
            slicer = choice["logprobs"]["text_offset"].index(len_input)
            res["output"]["echo_logprobs"] = {
                "tokens": choice["logprobs"]["tokens"][:slicer],
                "token_logprobs": choice["logprobs"]["token_logprobs"][:slicer],
            }

        # Gather tokens and calculate overall probability for completion.
        tokens_list = []
        logprob_sum = 0
        tokens = res["output"]["echo_logprobs"]["tokens"]
        token_logprobs = res["output"]["echo_logprobs"]["token_logprobs"]
        for i in range(1, completion_is_last_n_tokens_of_echoed_prompt + 1):
            tokens_list.append(tokens[-i])
            logprob_sum += token_logprobs[-i]
        tokens_list.reverse()
        results["tokens"].append("-".join(tokens_list))
        results["probability"].append(math.exp(logprob_sum))

    df_results = pd.DataFrame(results)

    return df_results