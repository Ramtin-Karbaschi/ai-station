# AI Station test suite

The canonical runner selects the installed gateway virtual environment and
runs every offline unit and cross-file contract test:

~~~bash
./scripts/test.sh
ai test
make test
~~~

The suite covers resource admission, model/API name consistency, gateway
message rewriting, OpenCode configuration safety, Graphify integration,
Windows Manager contracts, model add/quarantine, and the repository
quality-gate contract. It does not start or switch a model.

Document extraction fixtures live under
`benchmarks/datasets/documents/`. Retrieval eval corpus lives under
`benchmarks/datasets/retrieval/` when present.

Live JSON-schema and tool-calling probes are optional and require a healthy
general llama.cpp server:


~~~bash
ai test --live
~~~

CI sets `AI_STATION_TEST_PYTHON=python` after installing the pinned gateway
requirements. Local runs use `.venvs/gateway/bin/python` when present.
