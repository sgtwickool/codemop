import pytest

# A realistic GitHub diff: a modified file with two hunks, an added file, a deleted file,
# a rename without changes, a binary file and a lock file
SAMPLE_DIFF = """\
diff --git a/app/service.py b/app/service.py
index 1111111..2222222 100644
--- a/app/service.py
+++ b/app/service.py
@@ -10,6 +10,7 @@ class Service:
     def __init__(self, client):
         self.client = client
-        self.cache = {}
+        self.cache = None
+        self.retries = 3
 
     def fetch(self, key):
         return self.client.get(key)
@@ -40,4 +41,4 @@ def helper(items):
     total = 0
     for item in items:
-        total += item
+        total += item.value
     return total
\\ No newline at end of file
diff --git a/app/new_module.py b/app/new_module.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/app/new_module.py
@@ -0,0 +1,3 @@
+def greet(name):
+    return "Hello " + name
+
diff --git a/old.txt b/old.txt
deleted file mode 100644
index 4444444..0000000
--- a/old.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-first
-second
diff --git a/docs/a.md b/docs/b.md
similarity index 100%
rename from docs/a.md
rename to docs/b.md
diff --git a/logo.png b/logo.png
index 5555555..6666666 100644
Binary files a/logo.png and b/logo.png differ
diff --git a/uv.lock b/uv.lock
index 7777777..8888888 100644
--- a/uv.lock
+++ b/uv.lock
@@ -1,1 +1,1 @@
-version = 1
+version = 2
"""


@pytest.fixture
def sample_diff() -> str:
    return SAMPLE_DIFF
