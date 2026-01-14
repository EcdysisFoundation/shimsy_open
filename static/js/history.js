function convertToLocalTime() {
    const timeElements = document.querySelectorAll('.utc-time');
    timeElements.forEach(element => {
        const utcTime = element.getAttribute('data-utc');
        if (utcTime) {
            try {
                const date = new Date(utcTime);
                const localTime = date.toLocaleString('en-US', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: 'numeric',
                    minute: '2-digit',
                    second: '2-digit',
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