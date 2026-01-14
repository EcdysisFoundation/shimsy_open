function convertToLocalTime() {
    const timeElements = document.querySelectorAll('.utc-time');
    timeElements.forEach(element => {
        const utcTime = element.getAttribute('data-utc');
        if (utcTime) {
            try {
                const date = new Date(utcTime);
                const localTime = date.toLocaleString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: false
                });
                element.textContent = localTime;
            } catch (error) {
 console.error('Error converting time:', error);
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', convertToLocalTime);

let currentRunFolder = '';

function showDiscardModal(runFolder) {
    currentRunFolder = runFolder;
    document.getElementById('modalRunFolder').textContent = runFolder;
    document.getElementById('discardModal').style.display = 'block';
}

function closeDiscardModal() {
    document.getElementById('discardModal').style.display = 'none';
    currentRunFolder = '';
}

function confirmDiscard() {
    if (currentRunFolder) {
        const confirmBtn = document.querySelector('.modal-footer .btn-danger');
        const originalText = confirmBtn.textContent;
        confirmBtn.textContent = 'Discarding...';
        confirmBtn.disabled = true;
        fetch('/discard-unstitched-run/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                run_folder: currentRunFolder
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert(`Successfully discarded run: ${currentRunFolder}\n\n${data.message}`);
                closeDiscardModal();
                window.location.reload();
            } else {
                alert(`Error discarding run: ${data.message}`);
                confirmBtn.textContent = originalText;
                confirmBtn.disabled = false;
            }
        })
        .catch(error => {
 console.error('Error:', error);
            alert(`Network error while discarding run: ${error.message}`);
            confirmBtn.textContent = originalText;
            confirmBtn.disabled = false;
        });
    }
}
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

window.onclick = function(event) {
    const modal = document.getElementById('discardModal');
    if (event.target === modal) {
        closeDiscardModal();
    }
}

document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeDiscardModal();
    }
});