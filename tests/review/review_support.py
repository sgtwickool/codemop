"""What the review tests share: a repository's files, as context reads them."""


class Files:
    """A FileSource over a dict of path: text, which remembers what was read"""

    def __init__(self, files):
        self.files = files
        self.read_paths = []

    async def read(self, path):
        self.read_paths.append(path)
        return self.files.get(path)

    async def paths(self):
        return list(self.files)
