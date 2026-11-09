# Fielding the survey: the checklist

The plan is fixed in [`PREREGISTRATION_SURVEY.md`](../PREREGISTRATION_SURVEY.md) and the questions in [`survey-instrument.md`](survey-instrument.md). This page is the order of work. Do the steps in order; each one protects the result.

## Before anything

1. **The plan is tagged.** `git tag -l prereg-survey` shows the tag, and the two hashes in the pre-registration match the files at that tag. Fielding starts after the tag, never before.
2. **You are free to run it.** Confirm that a personal research survey is allowed under any employer policy on outside projects. This is yours to check; nothing in the project depends on an employer.
3. **Choose a panel that can screen.** It must let you require "US adult, took a domestic connecting flight in the last 12 months", exclude people in travel, insurance or market research, and pay respondents. Check its current price and its data-protection terms (you are in the EU; the respondents are in the US): ask for anonymous respondent codes only and confirm you receive no personal data.

## Build

4. **Import the question bank** (`docs/survey-question-bank.csv`) into a survey tool that can randomize. Per respondent: one connection and one wording at random, then the six price questions in a random order, each with the four answer options exactly as in the bank (`Definitely would`, `Probably would`, `Probably would not`, `Definitely would not`).
5. **Add** the screening questions, the consent text below, one attention-check item that asks for a specific answer, and a hidden completion-time timer.
6. **Export format:** one row per respondent × price, columns `respondent, scenario, wording, mult, answer, attention_ok, seconds`, with `answer` mapped to `definitely`, `probably` or `no`. A respondent who fails the check has `attention_ok` false.

**Consent text (shown before the first question).** "This is an independent research survey about a possible travel product. It takes about eight minutes. We do not ask for your name or any contact details. You can stop at any time. Your answers are used only for this research and are published only in aggregate."

## Pilot

7. **Run up to 20 respondents** to check that the wording is understood and the timing is right. Their answers are excluded. If you change anything, update the files, recompute the two hashes, and tag again before the main fielding (a new tag, `prereg-survey-2`, with the reason written in it).

## Field

8. **Collect until 400 respondents pass the checks** (at most 800 in total). Do not look at any answers until the 400 exist.
9. **Export the CSV** to `responses.csv`. Keep the raw file out of the repository if the panel's terms require it; only the analysis output is published.

## Analyse and publish

10. **Run** `python -m mcp.survey analyse responses.csv` (from `src`; inside the project's Docker image if Windows blocks pandas). It prints one line and writes `results/survey_results.json`.
11. **Publish whatever it says.** Add a new Part to `VALIDATION.md` with the numbers, update the README limits row on demand, and commit them together. A result that rules the cover out at 3% or 10% goes in as prominently as one that does not.
12. **Read it correctly.** A pass means only that the experiment is not ruled out. It does not show the cover would sell.
