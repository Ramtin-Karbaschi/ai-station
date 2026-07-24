# Experimental / unused infrastructure notes
#
# The former Caddy reverse-proxy config and Prometheus scrape config
# targeted services (`api`, `web`) that are not part of the active Compose
# stack. They were removed in Phase 1 to eliminate documentation drift.
#
# Observability policy is defined in docs/adr/ADR-007-observability-boundary.md:
# prefer engine-native metrics and verify.sh signals before adding a full
# Prometheus/Grafana stack.
