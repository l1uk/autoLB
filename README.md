# Developer guide

For starting backend, run

`
docker compose -f backend/docker-compose.yml up
`

It will start backend infrastructure with hot reload.

To run tests, run

`
docker compose -f backend/docker-compose.yml run --rm backend pytest backend/tests/ -v
`