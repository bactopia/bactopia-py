"""Auto-detect host resources and emit Nextflow CLI overrides for local profiles."""

import psutil
import rich
import rich.console
import rich.traceback
import rich_click as click

import bactopia

# Set up Rich
stderr = rich.console.Console(stderr=True)
rich.traceback.install(console=stderr, width=200, word_wrap=True, extra_lines=1)
click.rich_click.USE_RICH_MARKUP = True

MEM_CAP = 144
MEM_FLOOR = 4
CPU_CAP = 12

LOCAL_PROFILES = frozenset(
    {
        "standard",
        "conda",
        "mamba",
        "docker",
        "arm",
        "apptainer",
        "singularity",
        "podman",
        "charliecloud",
        "shifter",
        "wave",
    }
)

INFORMATIONAL_FLAGS = frozenset({"--help", "-h", "--help_all", "--list_wfs"})


def _flag_value(args, *flag_names):
    """Return the value of the first matching flag in args, or None."""
    for i, arg in enumerate(args):
        for flag in flag_names:
            if arg == flag:
                return args[i + 1] if i + 1 < len(args) else ""
            if arg.startswith(f"{flag}="):
                return arg[len(flag) + 1 :]
    return None


def _has_flag(args, *flag_names):
    """True if any of flag_names appears in args (bare or `flag=value`)."""
    return _flag_value(args, *flag_names) is not None


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def sysinfo(ctx, args):
    """Auto-detect host RAM and CPUs, emit Nextflow CLI fragments for local profiles.

    Reads the bactopia wrapper's argv as a passthrough. Emits to stdout the
    additional `--max_memory <N>.GB` / `--max_cpus <N>` flags that should be
    appended to the `nextflow run` command line. Emits nothing when:

      - a custom config is supplied (`-c` or `--nfconfig`)
      - any `-profile` value is not in the local-executor allow-list
      - both `--max_memory` and `--max_cpus` are already set by the user
      - the invocation is informational (`--help`, `--help_all`, `--list_wfs`)
    """
    if args == ("--version",) or args == ("-V",):
        click.echo(f"bactopia-sysinfo {bactopia.__version__}")
        return

    if any(a in INFORMATIONAL_FLAGS for a in args):
        return

    if _has_flag(args, "-c", "--nfconfig"):
        return

    profile = _flag_value(args, "-profile", "--profile")
    profiles = set(profile.split(",")) if profile else {"standard"}
    if not profiles.issubset(LOCAL_PROFILES):
        return

    additions = []

    if not _has_flag(args, "--max_memory"):
        total_gb = psutil.virtual_memory().total // (1024**3)
        mem = min(total_gb - 1, MEM_CAP)
        if mem >= MEM_FLOOR:
            if mem != MEM_CAP:
                additions.append(f"--max_memory {mem}.GB")
        else:
            click.echo(
                f"[bactopia-sysinfo] detected only {total_gb} GB RAM "
                f"(below floor of {MEM_FLOOR} GB); skipping --max_memory",
                err=True,
            )

    if not _has_flag(args, "--max_cpus"):
        cpus = min(psutil.cpu_count(logical=True) or 1, CPU_CAP)
        if cpus != CPU_CAP:
            additions.append(f"--max_cpus {cpus}")

    if additions:
        line = " ".join(additions)
        if line:
            click.echo(line)
            click.echo(f"[bactopia-sysinfo] auto-detected: {line}", err=True)


def main():
    sysinfo()


if __name__ == "__main__":
    main()
