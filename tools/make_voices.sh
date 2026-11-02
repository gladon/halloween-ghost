V=${ELEVENLABS_VOICE_ID:-jBpfuIE2acCO8z3wKNLl}   # ElevenLabs "Gigi" (childlike); any voice id works
say() { curl -sS -o "raw_$1.mp3" -w "$1 %{http_code}\n" "https://api.elevenlabs.io/v1/text-to-speech/$V?output_format=mp3_44100_128" -H "xi-api-key: $ELEVENLABS_API_KEY" -H "Content-Type: application/json" -d "{\"text\":\"$2\",\"model_id\":\"eleven_v3\",\"voice_settings\":{\"stability\":0.3,\"similarity_boost\":0.75,\"style\":0.8}}"; file "raw_$1.mp3" | grep -q Audio || { echo "BAD $1 $(head -c 150 raw_$1.mp3)"; rm -f raw_$1.mp3; }; }
say hi "[giggles] Hiii! Wave at me!"
say hi2 "[excited] Ooh, visitors! [giggles] Wave hello!"
say wheee "[delighted] Wheeeee!"
say boo "[playfully] Boo! [giggles] Hee hee hee!"
say sneeze "Ah... ah... ACHOO! [giggles] Oopsie!"
say tada "[cheerfully] Ta-da! Do you like my hat?"
say triplets "[giggles] Now there are three of us!"
say bat "[excited] This is my friend Batty!"
say hic "Hic! [giggles] Hic! Oh no! Hic!"
say candy "[cheerfully] Happy Halloween!"
say golden "[gasps] Wow! You found the golden ghost!"
