import subprocess
import sys

def cmd_oe(cmd_line):
    '''
        Purpose: Return stdout and stderr of a shell command.
    '''
    o = []
    e = []
    p = subprocess.Popen (cmd_line,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,)
    try:
        #for line in iter(p.stdout.readline, b""):
        o = [line.decode('utf-8').strip() for line in iter(p.stdout.readline, b"")]
        e = [line.decode('utf-8').strip() for line in iter(p.stderr.readline, b"")]
    finally:
        p.stdout.close()
        p.stderr.close()
        return (o, e)


def main():
    print('Nothing here..., for use as a library')

if __name__ == '__main__':
    main()
