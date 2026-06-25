# Security Reviews

This folder holds LLM generated security reviews. Note that they may be out of sync with the code but should be close enough.

**Summary**: Neither one identifies an issue that can cause data loss or exfiltration. They report some issues that can lead to denial-of-service but even they are minimal. While the library itself exposes direct SQL on the database (as intended), it is no *more* access than one would have when they chose the tool.