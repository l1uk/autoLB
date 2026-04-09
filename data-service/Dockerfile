FROM golang:1.23 AS dev

WORKDIR /workspace/data-service
ENV CGO_ENABLED=0

FROM golang:1.23 AS deps
WORKDIR /src
COPY go.mod ./
RUN go mod download

FROM deps AS build-linux-amd64
WORKDIR /src
COPY . .
ENV CGO_ENABLED=0 GOOS=linux GOARCH=amd64
RUN go build -o /out/agent-linux-amd64 ./cmd/agent

FROM deps AS build-windows-amd64
WORKDIR /src
COPY . .
ENV CGO_ENABLED=0 GOOS=windows GOARCH=amd64
RUN go build -o /out/agent-windows-amd64.exe ./cmd/agent
