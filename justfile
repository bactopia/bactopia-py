PROJECT := "bactopia"
OPEN := if os() == "macos" { "open" } else { "xdg-open" }
VERSION := `poetry version -s`

# format code with ruff
fmt:
    poetry run ruff format .
    poetry run ruff check --fix .

# check format and lint with ruff
check-fmt:
    poetry run ruff format --check .

# lint code with ruff
lint:
    poetry run ruff check .

# install latest version with poetry
install:
    poetry install --no-interaction

# check formatting, linting, and tests
check: check-fmt lint

# run tests
test *ARGS:
    poetry run pytest {{ARGS}}

# run tests with coverage report
test-cov *ARGS:
    poetry run pytest --cov=bactopia --cov-report=term-missing {{ARGS}}

# run only unit tests (no external data needed)
test-unit:
    poetry run pytest -m "not integration" --tb=short

# prints out the commands to run to tag the release and push it
tag:
    @echo "Run \`git tag -a {{ VERSION }} -m <message>\` to tag the release"
    @echo "Then run \`git push origin {{ VERSION }}\` to push the tag"

# recreate the poetry lock file
relock:
    poetry lock --no-interaction

# build a python release
build:
    poetry build --no-interaction
