let mediaRecorder;
let audioChunks = [];
let audioBlob;
let transcriptText = "";
const controlButton = document.getElementById('controlButton');
const learnPronunciationButton = document.getElementById('learnPronunciationButton');
const transcriptField = document.getElementById('transcript');
const audioPlayer = document.getElementById('audioPlayer');
const scoresTable = document.querySelector('#scoresTable tbody');
const phonemeButton = document.getElementById('phonemeButton');
const phonemeDetails = document.querySelector('.phoneme-details');
const phonemeTable = document.getElementById('phonemeTable');

controlButton.addEventListener('click', async () => {
    if (controlButton.textContent === 'Start Recording') {
        await startRecording();
    } else if (controlButton.textContent === 'Stop Recording') {
        stopRecording();
    } else if (controlButton.textContent === 'Refresh') {
        resetUI();
    }
});

async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = event => audioChunks.push(event.data);

    mediaRecorder.start();
    controlButton.textContent = 'Stop Recording';
}

function stopRecording() {
    mediaRecorder.stop();
    mediaRecorder.onstop = async () => {
        audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        audioPlayer.src = URL.createObjectURL(audioBlob);
        audioPlayer.load();

        const formData = new FormData();
        formData.append('audio', audioBlob, 'audio.wav');

        try {
            const response = await fetch('/ackaud', {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();
            const whisperResult = data.whisper_result;
            const pronunciationResult = data.pronunciation_result.NBest[0];

            transcriptText = whisperResult.text;
            transcriptField.textContent = transcriptText;

            const ieltsBandScore = data.IELTS_band_score; // Extract the IELTS band score from the response
                
            // Update the IELTS Band Score section
            const ieltsBandElement = document.getElementById('ieltsBand');
            ieltsBandElement.textContent = `IELTS Band Score: ${ieltsBandScore}`;

            scoresTable.innerHTML = 
                `<tr>
                    <td>${pronunciationResult.AccuracyScore}</td>
                    <td>${pronunciationResult.CompletenessScore}</td>
                    <td>${pronunciationResult.FluencyScore}</td>
                    <td>${pronunciationResult.PronScore.toFixed(1)}</td>
                </tr>`;

            populatePhonemeTable(pronunciationResult.Words);

            phonemeButton.style.display = 'inline-block';
            learnPronunciationButton.style.display = 'inline-block';

        } catch (error) {
            alert('Error: ' + error.message);
        }
    };
    controlButton.textContent = 'Refresh';
}

learnPronunciationButton.addEventListener('click', async () => {
    if (!transcriptText) {
        alert('No transcript available for pronunciation.');
        return;
    }

    const formData = new FormData();
    formData.append('reftext', transcriptText);

    try {
        const response = await fetch('/gettts', {
            method: 'POST',
            body: formData,
        });

        if (response.ok) {
            const audioBlob = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            audioPlayer.src = audioUrl;
            audioPlayer.load();
            audioPlayer.play();
        } else {
            alert('Failed to fetch the pronunciation audio.');
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
});

function populatePhonemeTable(words) {
    let tableHTML = '<thead><tr><th>Word</th><th>Word Accuracy</th><th>Phoneme</th><th>Phoneme Accuracy</th></tr></thead><tbody>';

    words.forEach(word => {
        tableHTML += `<tr><td rowspan="${word.Phonemes.length + 1}">${word.Word}</td><td rowspan="${word.Phonemes.length + 1}">${word.AccuracyScore}</td></tr>`;
        word.Phonemes.forEach(phoneme => {
            tableHTML += `<tr><td>${phoneme.Phoneme}</td><td>${phoneme.AccuracyScore}</td></tr>`;
        });
    });

    tableHTML += '</tbody>';
    phonemeTable.innerHTML = tableHTML;
}

phonemeButton.addEventListener('click', () => {
    if (phonemeDetails.style.display === 'none') {
        phonemeDetails.style.display = 'block';
    } else {
        phonemeDetails.style.display = 'none';
    }
});

function resetUI() {
    transcriptText = '';
    //transcriptField.value = '';
    transcriptField.textContent = '';
    audioPlayer.src = '';
    scoresTable.innerHTML = '';
    phonemeTable.innerHTML = '';
    phonemeDetails.style.display = 'none';
    phonemeButton.style.display = 'none';
    learnPronunciationButton.style.display = 'none';
    controlButton.textContent = 'Start Recording';
    controlButton.disabled = false;
}
