#!/usr/bin/env python3
"""
Edge TTS Service Test Script
Tests if Microsoft Edge TTS service is working independently of Maxi AI code.
"""
import asyncio
import edge_tts
import os
import sys
from datetime import datetime

# Test voices - same ones used in Maxi AI
TEST_VOICES = [
    "en-US-EmmaNeural",
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-GB-SoniaNeural",
    "en-US-GuyNeural"
]

TEST_TEXT = "Hello! This is a test of the Edge TTS service."


async def test_single_voice(voice: str, output_file: str):
    """Test a single voice and save audio if successful."""
    print(f"\n{'='*60}")
    print(f"🎤 Testing voice: {voice}")
    print(f"{'='*60}")

    try:
        # Create Edge TTS communicate object
        communicate = edge_tts.Communicate(
            text=TEST_TEXT,
            voice=voice,
            rate="+0%",
            pitch="-2Hz"
        )

        print(f"⏳ Attempting to generate audio...")

        # Try to generate audio
        audio_data = bytearray()
        chunk_count = 0

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
                chunk_count += 1

        if len(audio_data) > 0:
            # Save to file
            with open(output_file, "wb") as f:
                f.write(audio_data)

            file_size_kb = len(audio_data) / 1024
            print(f"✅ SUCCESS!")
            print(
                f"   - Generated {len(audio_data)} bytes ({file_size_kb:.2f} KB)")
            print(f"   - Received {chunk_count} audio chunks")
            print(f"   - Saved to: {output_file}")
            return True
        else:
            print(f"❌ FAILED: No audio data received")
            return False

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        print(f"❌ FAILED: {error_type}")
        print(f"   Error: {error_msg}")

        # Check for specific errors
        if "403" in error_msg or "Invalid response status" in error_msg:
            print(f"   🚫 This is a 403 Forbidden error (rate limiting/blocking)")
            print(f"   Microsoft Edge TTS is blocking your requests")
        elif "Connection" in error_msg or "timeout" in error_msg.lower():
            print(f"   🌐 This is a connection error")
            print(f"   Check your internet connection")
        elif "SSL" in error_msg or "certificate" in error_msg.lower():
            print(f"   🔒 This is an SSL/certificate error")

        return False


async def test_edge_tts_service():
    """Run comprehensive Edge TTS service test."""
    print("\n" + "="*60)
    print("🔊 EDGE TTS SERVICE TEST")
    print("="*60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Python Version: {sys.version}")
    print(
        f"Edge-TTS Package: {edge_tts.__version__ if hasattr(edge_tts, '__version__') else 'Unknown'}")

    # Test internet connectivity
    print(f"\n🌐 Testing internet connectivity...")
    try:
        import socket
        socket.create_connection(("www.google.com", 80), timeout=5)
        print(f"✅ Internet connection OK")
    except Exception as e:
        print(f"❌ Internet connection FAILED: {e}")
        print(f"   Cannot proceed without internet")
        return

    # Create output directory
    output_dir = "tts_test_output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"\n📁 Created output directory: {output_dir}")

    # Test each voice
    results = {}
    for i, voice in enumerate(TEST_VOICES, 1):
        output_file = os.path.join(
            output_dir, f"test_{voice.replace('-', '_')}.mp3")
        success = await test_single_voice(voice, output_file)
        results[voice] = success

        # Add delay between tests to avoid rate limiting
        if i < len(TEST_VOICES):
            print(f"\n⏳ Waiting 2 seconds before next test...")
            await asyncio.sleep(2)

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 TEST SUMMARY")
    print(f"{'='*60}")

    successful = sum(1 for v in results.values() if v)
    failed = len(results) - successful

    print(f"\n✅ Successful: {successful}/{len(results)}")
    print(f"❌ Failed: {failed}/{len(results)}")

    print(f"\nResults by voice:")
    for voice, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} - {voice}")

    # Diagnosis
    print(f"\n{'='*60}")
    print(f"🔍 DIAGNOSIS")
    print(f"{'='*60}")

    if successful == 0:
        print(f"\n❌ ALL TESTS FAILED")
        print(f"\nPossible causes:")
        print(f"  1. Microsoft Edge TTS is blocking your IP/server")
        print(f"  2. Railway/cloud provider IP is rate-limited")
        print(f"  3. Edge TTS service is down")
        print(f"  4. Network firewall blocking WebSocket connections")
        print(f"\nRecommendations:")
        print(f"  - Try running from a different network/location")
        print(f"  - Consider alternative TTS services (Google Cloud TTS, Amazon Polly)")
        print(f"  - Check if Railway supports WebSocket connections to speech.platform.bing.com")
        print(f"  - Wait 24 hours and retry (rate limit may reset)")
    elif successful < len(results):
        print(f"\n⚠️ PARTIAL SUCCESS")
        print(f"\nSome voices work, others don't.")
        print(f"Working voices should be used in Maxi AI.")
    else:
        print(f"\n✅ ALL TESTS PASSED")
        print(f"\nEdge TTS service is working fine!")
        print(f"The issue is likely in Maxi AI's code, not the Edge TTS service.")

    print(f"\n{'='*60}")
    print(f"Test complete! Check {output_dir}/ for generated audio files.")
    print(f"{'='*60}\n")


def main():
    """Main entry point."""
    try:
        asyncio.run(test_edge_tts_service())
    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test script error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
