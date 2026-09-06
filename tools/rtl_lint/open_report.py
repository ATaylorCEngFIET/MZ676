"""Open a generated local HTML report in the default browser."""
from pathlib import Path
import sys
import webbrowser


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print('Expected one local HTML report path', file=sys.stderr)
        return 2
    path = Path(args[0]).resolve()
    if not path.is_file() or path.suffix.lower() != '.html':
        print('Run RTL Lint first: formatted report is missing', file=sys.stderr)
        return 2
    try:
        if not webbrowser.open(path.as_uri(), new=2):
            raise OSError('No browser accepted the local report')
    except (OSError, webbrowser.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
