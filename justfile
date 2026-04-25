PROJECT := "bactopia"
OPEN := if os() == "macos" { "open" } else { "xdg-open" }
POETRY := `which poetry`
PYTHON := `which python`
VERSION := `poetry version -s`

# format code with ruff
fmt:
    {{POETRY}} run ruff format .
    {{POETRY}} run ruff check --fix .

# check format and lint with ruff
check-fmt:
    {{POETRY}} run ruff format --check .

# lint code with ruff
lint:
    {{POETRY}} run ruff check .

# install latest version with poetry
install:
    {{POETRY}} install --no-interaction --with test

# check formatting, linting, and tests
check: check-fmt lint

# run tests
test *ARGS:
    {{POETRY}} run {{PYTHON}} -m pytest {{ARGS}}

# run tests with coverage report
test-cov *ARGS:
    {{POETRY}} run {{PYTHON}} -m pytest --cov=bactopia --cov-report=term-missing {{ARGS}}

# run only unit tests (no external data needed)
test-unit:
    {{POETRY}} run {{PYTHON}} -m pytest -m "not integration" --tb=short

# prints out the commands to run to tag the release and push it
tag:
    @echo "Run \`git tag -a {{ VERSION }} -m <message>\` to tag the release"
    @echo "Then run \`git push origin {{ VERSION }}\` to push the tag"

# recreate the poetry lock file
relock:
    {{POETRY}} lock --no-interaction

# build a python release
build:
    {{POETRY}} build --no-interaction
