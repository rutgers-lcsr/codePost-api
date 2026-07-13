#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.

export DEBUG=TRUE
export AUTOGRADER_AUTO_EXECUTE=TRUE
export CELERY_TASK_ALWAYS_EAGER=TRUE
export WATCHFILES_FORCE_POLLING="${WATCHFILES_FORCE_POLLING:-TRUE}"

LOCAL_MODE=FALSE
LOAD_ENV=FALSE
START_FLOWER=FALSE
FLOWER_PORT=5555
FLOWER_PORT_SET=FALSE

while [[ $# -gt 0 ]]; do
	case "$1" in
		--local)
			LOCAL_MODE=TRUE
			shift
			;;
		--env)
			LOAD_ENV=TRUE
			shift
			;;
		--flower)
			START_FLOWER=TRUE
			shift
			;;
		--flower-port)
			if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
				# Use Flower default when no value is provided
				shift
				continue
			fi
			FLOWER_PORT="$2"
			FLOWER_PORT_SET=TRUE
			shift 2
			;;
		--flower-port=*)
			FLOWER_PORT="${1#*=}"
			if [[ -z "$FLOWER_PORT" ]]; then
				# Use Flower default when no value is provided
				shift
				continue
			fi
			FLOWER_PORT_SET=TRUE
			shift
			;;
		*)
			echo "[dev] Unknown option: $1"
			exit 1
			;;
	esac
done

if [[ "$LOAD_ENV" == "TRUE" && -f ".env" ]]; then
	set -a
	source .env
	set +a
else
	# Ensure local defaults when not loading .env
	unset DB_HOSTNAME DB_NAME DB_USERNAME DB_PASSWORD DB_PORT
	unset WORKER_SHELL_WS_URL WORKER_SHELL_SHARED_SECRET
	# Preserve explicitly exported Redis settings
	if [[ -z "${WORKER_SHELL_REDIS_URL:-}" ]]; then
		unset WORKER_SHELL_REDIS_URL
	fi
	if [[ -z "${CELERY_BROKER_URL:-}" ]]; then
		unset CELERY_BROKER_URL
	fi
fi

source .venv/bin/activate

PIDS=()
cleanup() {
	for pid in "${PIDS[@]}"; do
		kill "$pid" 2>/dev/null || true
	done
}
trap cleanup EXIT
trap "cleanup; exit 130" INT TERM

if [[ "$LOCAL_MODE" == "TRUE" ]]; then
	export WORKER_SHELL_FORCE_LOCAL=TRUE
else
	if [[ -z "${WORKER_SHELL_REDIS_URL:-}" ]]; then
		export WORKER_SHELL_REDIS_URL="${CELERY_BROKER_URL}"
	fi
	if [[ -z "${WORKER_SHELL_REDIS_URL:-}" ]]; then
		export WORKER_SHELL_FORCE_LOCAL=TRUE
		echo "[dev] No Redis configured; running in local shell mode."
	else
		python -m autograder.worker_shell_relay &
		PIDS+=("$!")
	fi
fi

if [[ "$START_FLOWER" == "TRUE" ]]; then
	FLOWER_BROKER_URL="${WORKER_SHELL_REDIS_URL:-${CELERY_BROKER_URL:-redis://localhost:6379}}"
	FLOWER_ARGS=()
	if [[ "$FLOWER_PORT_SET" == "TRUE" ]]; then
		FLOWER_ARGS+=("--port" "$FLOWER_PORT")
	fi
	celery -A autograder --broker "$FLOWER_BROKER_URL" flower "${FLOWER_ARGS[@]}" &
	PIDS+=("$!")
	if [[ "$FLOWER_PORT_SET" == "TRUE" ]]; then
		echo "[dev] Flower started on http://localhost:$FLOWER_PORT"
	else
		echo "[dev] Flower started on http://localhost:5555"
	fi
fi

uvicorn codepost.asgi:application --host 0.0.0.0 --port 8000 --reload --reload-dir "$PWD"