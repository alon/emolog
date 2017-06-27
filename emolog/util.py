import os

def which(filename):
    path = os.environ.get('PATH', '.').split(os.pathsep)
    for d in path:
        if os.path.exists(os.path.join(d, filename)):
            return os.path.join(d, filename)
    return None

