import time


def main() -> None:
    for step in range(1, 6):
        print(f"Training step {step}/5...", flush=True)
        time.sleep(1)
    print("Training complete.", flush=True)


if __name__ == "__main__":
    main()

