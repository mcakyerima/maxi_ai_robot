import os
import torch
import onnx
import onnxruntime as ort
import numpy as np
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
from brain.intent_matcher_2 import IntentType

LOCAL_MODEL_DIR = "./local_model_cache/distilbert-base-uncased"
ONNX_MODEL_PATH = "intent_model.onnx"
MAX_LENGTH = 128
NUM_LABELS = len(IntentType)

# --- HELPER FUNCTIONS ---
def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()

# --- DOWNLOAD + SAVE MODEL IF NEEDED ---
def ensure_local_model():
    if os.path.exists(LOCAL_MODEL_DIR) and os.path.isfile(os.path.join(LOCAL_MODEL_DIR, "pytorch_model.bin")):
        print("✅ Local model files found.")
        return
    print("⬇ Downloading and saving model + tokenizer...")
    tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased")
    model = DistilBertForSequenceClassification.from_pretrained("distilbert-base-uncased", num_labels=NUM_LABELS)
    tokenizer.save_pretrained(LOCAL_MODEL_DIR)
    model.save_pretrained(LOCAL_MODEL_DIR)
    print(f"✅ Model saved at {LOCAL_MODEL_DIR}")

# --- EXPORT TO ONNX IF NEEDED ---
def ensure_onnx_export():
    if os.path.exists(ONNX_MODEL_PATH):
        print(f"✅ ONNX model already exists at {ONNX_MODEL_PATH}")
        return
    print("⚡ Exporting to ONNX...")
    tokenizer = DistilBertTokenizer.from_pretrained(LOCAL_MODEL_DIR)
    model = DistilBertForSequenceClassification.from_pretrained(LOCAL_MODEL_DIR, num_labels=NUM_LABELS)
    model.eval()

    dummy_input = tokenizer(
        "dummy input for onnx export",
        return_tensors="pt",
        padding="max_length",
        truncation=True,
        max_length=MAX_LENGTH
    )

    torch.onnx.export(
        model,
        (dummy_input["input_ids"], dummy_input["attention_mask"]),
        ONNX_MODEL_PATH,
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={"input_ids": {0: "batch_size"}, "attention_mask": {0: "batch_size"}},
        opset_version=12
    )
    print(f"✅ ONNX model exported to {ONNX_MODEL_PATH}")

# --- ONNX INFERENCE ---
class ONNXIntentMatcher:
    def __init__(self, onnx_path, tokenizer_dir):
        self.session = ort.InferenceSession(onnx_path)
        self.tokenizer = DistilBertTokenizer.from_pretrained(tokenizer_dir)
        self.intent_labels = [intent.value for intent in IntentType]

    def infer(self, text):
        enc = self.tokenizer(
            text,
            return_tensors="np",
            padding="max_length",
            truncation=True,
            max_length=MAX_LENGTH
        )
        logits = self.session.run(None, {
            "input_ids": enc["input_ids"],
            "attention_mask": enc["attention_mask"]
        })[0]
        probs = softmax(logits[0])
        best_idx = int(np.argmax(probs))
        return self.intent_labels[best_idx], float(probs[best_idx])

# --- TEST SUITE ---
def run_test_suite(matcher):
    test_cases = [
        ("summarize the entire chart that i had with you today", "conversation_summary"),
        ("What is 5 plus 3?", "math_calculation"),
        ("Twelve minus four", "math_calculation"),
        ("Six times seven", "math_calculation"),
        ("Calculate 24 x 3", "math_calculation"),
        ("What is 100 - 40?", "math_calculation"),
        ("What time is it?", "time_date"),
        ("What's the current time?", "time_date"),
        ("What day is today?", "time_date"),
        ("Tell me the time", "time_date"),
        ("What's the weather in Borno state?", "weather"),
        ("How's the weather in Maiduguri?", "weather"),
        ("Will it rain tomorrow?", "weather"),
        ("Should I wear a jacket this morning?", "weather"),
        ("What did we talk about today?", "conversation_summary"),
        ("Recap our conversation", "conversation_summary"),
        ("Summary of our chat", "conversation_summary"),
        ("What have we discussed?", "conversation_summary"),
        ("Maxi shut down", "shutdown"),
        ("Power off please", "shutdown"),
        ("Go to sleep", "shutdown"),
        ("Goodbye Maxi", "shutdown"),
        ("Tell me a joke", "joke_request"),
        ("Tell me a story", "story_request"),
        ("Let's play a game", "game_request"),
        ("Help me with homework", "homework_help"),
        ("How does photosynthesis work?", "learning_question"),
        ("Hello Maxi", "greeting"),
        ("You're awesome", "compliment_praise"),
        ("I need help", "help_request"),
        ("I'm sleepy", "bedtime_routine"),
        ("Can you help me with math homework?", "homework_help"),
        ("What time should I go to sleep?", "bedtime_routine"),
        ("Is the weather good for sleeping outside?", "weather"),
        ("Tell me about your day", "general_chat"),
        ("What do you think about robots?", "general_chat")
    ]

    correct = 0
    total = len(test_cases)
    print("\n🧪 ONNX Intent Matcher Test Results")
    print("=" * 60)

    for text, expected in test_cases:
        predicted, conf = matcher.infer(text)
        status = "✅" if predicted == expected else "❌"
        print(f"{status} Input: {text}")
        print(f"    Expected: {expected}")
        print(f"    Predicted: {predicted} (conf: {conf:.3f})\n")
        if predicted == expected:
            correct += 1

    acc = (correct / total) * 100
    print("=" * 60)
    print(f"🎯 Accuracy: {correct}/{total} ({acc:.2f}%)")

# --- MAIN ---
if __name__ == "__main__":
    ensure_local_model()
    ensure_onnx_export()

    matcher = ONNXIntentMatcher(ONNX_MODEL_PATH, LOCAL_MODEL_DIR)
    run_test_suite(matcher)
