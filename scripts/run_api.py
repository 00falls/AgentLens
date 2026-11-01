import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "agentlens.api:app", host="127.0.0.1", port=8000, loop="agentlens.checkpoints:loop_factory"
    )
