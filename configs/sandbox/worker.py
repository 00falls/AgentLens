"""Linux sandbox supervisor: generated code runs only in the child with bounded resources."""

import json
import os
import resource
import signal
import subprocess
import sys
import tempfile


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))


def main():
    request = json.load(sys.stdin)
    with tempfile.TemporaryDirectory(dir="/sandbox") as directory:
        with open(f"{directory}/logs.json", "w") as stream:
            json.dump(request["logs"], stream)
        with open(f"{directory}/analysis.py", "w") as stream:
            stream.write("import json\nlogs=json.load(open('logs.json'))\n" + request["code"])
        with open(f"{directory}/stdout", "wb") as out, open(f"{directory}/stderr", "wb") as err:
            process = subprocess.Popen(
                [sys.executable, "-I", "analysis.py"], cwd=directory,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
                stdout=out, stderr=err, preexec_fn=limits, start_new_session=True,
            )
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                print(json.dumps({"status": "timeout", "limit_seconds": 8}))
                return
        if process.returncode:
            with open(f"{directory}/stderr", "rb") as stream:
                error = stream.read(4096).decode("utf-8", errors="replace")
            print(json.dumps({"status": "error", "exit_code": process.returncode,
                              "stderr": error}))
            return
        with open(f"{directory}/stdout", "rb") as stream:
            result = json.loads(stream.read(65536))
        print(json.dumps({"status": "ok", "result": result}))


if __name__ == "__main__":
    main()
