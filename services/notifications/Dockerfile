FROM golang:1.23-alpine AS builder
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/notifications .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/notifications /notifications
ENV PORT=8080
EXPOSE 8080
ENTRYPOINT ["/notifications"]
