# Developer guide

For starting backend, run

`
docker compose -f backend/docker-compose.yml up
`

It will start backend infrastructure with hot reload.

For starting data-service, run

`
docker compose -f data-service/docker-compose.yml up
`


To run tests, run

`
docker compose -f backend/docker-compose.yml run --rm backend pytest backend/tests/ -v
`

For the data service, run 

`
docker compose -f data-service/docker-compose.yml run --rm agent go test ./... -v
`