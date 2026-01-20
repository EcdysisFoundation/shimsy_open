// Rescan Samples Page JavaScript
// Handles rescan trigger functionality

// Convert UTC times to local time
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

// Trigger rescan for selected dish+sample
async function handleTriggerRescan() {
    const sampleSelect = document.getElementById('sample-select');
    const dishSelect = document.getElementById('dish-select');
    const nameInput = document.getElementById('rescan-name');
    const name2Input = document.getElementById('rescan-name2');
    
    const rescanRequestId = sampleSelect ? sampleSelect.value : null;
    const dishNumber = dishSelect ? dishSelect.value : null;
    const name = nameInput ? nameInput.value.trim() : '';
    const name2 = name2Input ? name2Input.value.trim() : '';
    
    if (!rescanRequestId) {
        alert('Please select a sample');
        return;
    }
    
    if (!dishNumber) {
        alert('Please select a dish number');
        return;
    }
    
    if (!name) {
        alert('Please enter your name');
        if (nameInput) nameInput.focus();
        return;
    }
    
    if (!confirm(`Start rescan for sample on dish ${dishNumber}? This will run the camera for this dish only.`)) {
        return;
    }
    
    const button = document.getElementById('triggerRescanButton');
    const originalText = button.innerHTML;
    
    try {
        button.disabled = true;
        button.innerHTML = '<div class="loading"></div> Starting scan...';
        
        const response = await fetch('/api/trigger-rescan/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                rescan_request_id: rescanRequestId,
                dish_number: dishNumber,
                name: name,
                name2: name2
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            alert(`Rescan started successfully!\n\nSample: ${result.sample_name}\nDish: ${result.dish_number}\n\nThe scan is now running. Check the home page for progress.`);
        } else {
            alert(`Error: ${result.message}`);
        }
        
    } catch (error) {
        console.error('Error triggering rescan:', error);
        alert('Error triggering rescan: ' + error.message);
    } finally {
        button.disabled = false;
        button.innerHTML = originalText;
    }
}

async function refreshRescanDropdown() {
    const sampleSelect = document.getElementById('sample-select');
    const rescanTable = document.querySelector('.rescan-table');
    const formSection = document.querySelector('.form-section');
    const emptyState = document.querySelector('.empty-state');
    
    if (!sampleSelect) {
        return;
    }
    
    try {
        const response = await fetch('/api/get-rescan-requests/');
        const result = await response.json();
        
        if (result.status === 'success') {
            const currentValue = sampleSelect.value;
            sampleSelect.innerHTML = '<option value="">Select a sample...</option>';
            
            // Add new options
            if (result.rescan_requests && result.rescan_requests.length > 0) {
                result.rescan_requests.forEach(req => {
                    const option = document.createElement('option');
                    option.value = req.id;
                    option.textContent = req.display_name;
                    sampleSelect.appendChild(option);
                });
                
                if (currentValue && !result.rescan_requests.find(r => r.id == currentValue)) {
                    sampleSelect.value = '';
                }
                
                if (rescanTable) rescanTable.style.display = '';
                if (formSection) formSection.style.display = '';
                if (emptyState) emptyState.style.display = 'none';
                
                updateRescanTable(result.rescan_requests);
            } else {
                if (rescanTable) rescanTable.style.display = 'none';
                if (formSection) formSection.style.display = 'none';
                if (emptyState) emptyState.style.display = 'block';
                
                sampleSelect.value = '';
                const dishSelect = document.getElementById('dish-select');
                if (dishSelect) dishSelect.value = '';
                const nameInput = document.getElementById('rescan-name');
                if (nameInput) nameInput.value = '';
                const name2Input = document.getElementById('rescan-name2');
                if (name2Input) name2Input.value = '';
            }
        }
    } catch (error) {
        console.error('Error refreshing rescan dropdown:', error);
    }
}

function updateRescanTable(rescanRequests) {
    const tableBody = document.querySelector('.rescan-table tbody');
    if (!tableBody) return;
    
    tableBody.innerHTML = '';
    rescanRequests.forEach(req => {
        const row = document.createElement('tr');
        let requestedAt;
        let timeStr = '';
        let utcTime = '';
        
        if (req.requested_at) {
            requestedAt = new Date(req.requested_at);
            timeStr = requestedAt.toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                hour12: false
            });
            utcTime = requestedAt.toISOString();
        } else {
            timeStr = 'N/A';
        }
        
        row.innerHTML = `
            <td><strong>${req.display_name || ''}</strong></td>
            <td>${req.site_number || ''}</td>
            <td>${req.sample_type || ''}</td>
            <td>${req.transect || ''}</td>
            <td>${utcTime ? `<span class="utc-time" data-utc="${utcTime}">${timeStr}</span>` : timeStr}</td>
        `;
        tableBody.appendChild(row);
    });
    
    // Convert times
    convertToLocalTime();
}

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    convertToLocalTime();
    
    const triggerRescanButton = document.getElementById('triggerRescanButton');
    if (triggerRescanButton) {
        triggerRescanButton.addEventListener('click', handleTriggerRescan);
    }
    

    setInterval(refreshRescanDropdown, 30000);
    
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            refreshRescanDropdown();
        }
    });
});
