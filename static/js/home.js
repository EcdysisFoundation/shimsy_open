window.currentFolderManagementData = null;
function copyPreviousDish(currentDish) {
  const previousDish = currentDish - 1;
  const previousSite = document.getElementById(`site${previousDish}`).value;
  const previousType = document.getElementById(`type${previousDish}`).value;
  const previousTime = document.getElementById(`time${previousDish}`).value;
  if (!previousSite && !previousType && !previousTime) {
    alert(`Dish ${previousDish} is empty. Please fill it first before copying.`);
    return;
  }
  const currentSiteInput = document.getElementById(`site${currentDish}`);
  const currentTypeSelect = document.getElementById(`type${currentDish}`);
  const currentTimeSelect = document.getElementById(`time${currentDish}`);
  if (previousSite) {
    currentSiteInput.value = previousSite;
  }
  if (previousType) {
    currentTypeSelect.value = previousType;
  }
  if (previousTime) {
    currentTimeSelect.value = previousTime;
  }
  const copyBtn = document.querySelector(`button[onclick="copyPreviousDish(${currentDish})"]`);
  const originalText = copyBtn.innerHTML;
  copyBtn.innerHTML = 'DONE';
  copyBtn.style.backgroundColor = '#28a745';
  setTimeout(() => {
    copyBtn.innerHTML = originalText;
    copyBtn.style.backgroundColor = '';
  }, 1000);
 console.log(`Copied data from Dish ${previousDish} to Dish ${currentDish}`);
}
const STITCHER_STATE_KEY = 'shimsy_stitcher_state';
const STITCHER_PROGRESS_KEY = 'shimsy_stitcher_progress';
const runBtn = document.getElementById("runButton");
const statusDiv = document.getElementById("status");

let controller = null;
let runRequest = null;
let stitchingInProgress = false;
let currentPreviewData = null;
let currentImageIndex = 0;
let currentFolderImages = [];
let currentRotation = 0;
let imageRotations = {};
let currentPage = 1;
const IMAGES_PER_PAGE = 20;
let totalPages = 1;
let folderDataCache = new Map();
const CACHE_EXPIRY = 5 * 60 * 1000;
let imageCache = new Map();
let imagePreloader = new Set();
const IMAGE_CACHE_EXPIRY = 10 * 60 * 1000;
const THUMBNAIL_SIZE = 'thumbnail';
const MEDIUM_SIZE = 'medium';
const FULL_SIZE = 'full';
const MAX_CONCURRENT_LOADS = 6;
const PRELOAD_BATCH_SIZE = 12;
async function loadAllRunFolders() {
  try {
    const response = await fetch('/get-all-runs/');
    const result = await response.json();
    if (result.status === 'success') {
      const select = document.getElementById('run-folder-select');
      select.innerHTML = '';
      const sortedRunFolders = result.run_folders.sort((a, b) => {
        const aNum = parseInt(a.name.replace('run_', ''));
        const bNum = parseInt(b.name.replace('run_', ''));
        return bNum - aNum;
      });
      sortedRunFolders.forEach(runFolder => {
        const option = document.createElement('option');
        option.value = runFolder.name;
        option.textContent = `${runFolder.name} (${runFolder.subfolder_count} folders)`;
        select.appendChild(option);
      });
      if (sortedRunFolders.length > 0) {
        const highestRun = sortedRunFolders[0].name;
        select.value = highestRun;
        loadRunInfo(highestRun);
      }
 console.log('Run folders refreshed successfully');
    } else {
 console.error('Failed to load run folders:', result.message);
    }
  } catch (error) {
 console.error('Error loading run folders:', error);
  }
}
async function getCachedFolderData(runFolder) {
  const cacheKey = runFolder || 'latest';
  const cached = folderDataCache.get(cacheKey);
  if (cached && (Date.now() - cached.timestamp) < CACHE_EXPIRY) {
 console.log(`Using cached folder data for ${cacheKey}`);
    return cached.data;
  }
 console.log(`Fetching fresh folder data for ${cacheKey}`);
  const url = runFolder ? `/get-run-subfolders/?run_folder=${runFolder}` : '/get-run-subfolders/';
  const response = await fetch(url);
  const data = await response.json();
  folderDataCache.set(cacheKey, {
    data: data,
    timestamp: Date.now()
  });
  return data;
}
function clearFolderDataCache() {
  folderDataCache.clear();
 console.log('Folder data cache cleared');
}
window.addEventListener('load', () => {
  setTimeout(clearFolderDataCache, 1000);
});
function preloadImage(imagePath, size = THUMBNAIL_SIZE, quality = 75) {
  const cacheKey = `${imagePath}_${size}_${quality}`;
  const cached = imageCache.get(cacheKey);
  if (cached && (Date.now() - cached.timestamp) < IMAGE_CACHE_EXPIRY) {
    return Promise.resolve(cached.url);
  }
  if (imagePreloader.has(cacheKey)) {
    return new Promise((resolve) => {
      const checkLoaded = () => {
        const cached = imageCache.get(cacheKey);
        if (cached) {
          resolve(cached.url);
        } else {
          setTimeout(checkLoaded, 50);
        }
      };
      checkLoaded();
    });
  }
  imagePreloader.add(cacheKey);
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = async () => {
      try {
        const response = await fetch(`/serve-image/?image_path=${encodeURIComponent(imagePath)}&size=${size}&quality=${quality}`);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        imageCache.set(cacheKey, {
          url: url,
          timestamp: Date.now(),
          size: size,
          quality: quality
        });
        imagePreloader.delete(cacheKey);
        resolve(url);
      } catch (error) {
        imagePreloader.delete(cacheKey);
        reject(error);
      }
    };
    img.onerror = () => {
      imagePreloader.delete(cacheKey);
      reject(new Error(`Failed to load image: ${imagePath}`));
    };
    img.src = `/serve-image/?image_path=${encodeURIComponent(imagePath)}&size=${size}&quality=${quality}`;
  });
}
function preloadImages(imagePaths, maxConcurrent = MAX_CONCURRENT_LOADS, size = THUMBNAIL_SIZE, quality = 75) {
  const results = [];
  let currentIndex = 0;
  let completed = 0;
  return new Promise((resolve) => {
    const loadNext = () => {
      if (currentIndex >= imagePaths.length) {
        if (completed === imagePaths.length) {
          resolve(results);
        }
        return;
      }
      const imagePath = imagePaths[currentIndex++];
      preloadImage(imagePath, size, quality)
        .then(url => {
          results.push({ path: imagePath, url: url, success: true });
        })
        .catch(error => {
          results.push({ path: imagePath, error: error, success: false });
        })
        .finally(() => {
          completed++;
          if (currentIndex < imagePaths.length) {
            setTimeout(loadNext, 50);
          } else if (completed === imagePaths.length) {
            resolve(results);
          }
        });
    };
    for (let i = 0; i < Math.min(maxConcurrent, imagePaths.length); i++) {
      setTimeout(loadNext, i * 25);
    }
  });
}
function clearImageCache() {
  for (const [key, cached] of imageCache.entries()) {
    if (cached.url && cached.url.startsWith('blob:')) {
      URL.revokeObjectURL(cached.url);
    }
  }
  imageCache.clear();
  imagePreloader.clear();
 console.log('Image cache cleared');
}
function preloadFullSizeOnHover(imagePath) {
  const cacheKey = `${imagePath}_${FULL_SIZE}_90`;
  const cached = imageCache.get(cacheKey);
  if (!cached || (Date.now() - cached.timestamp) > IMAGE_CACHE_EXPIRY) {
    preloadImage(imagePath, FULL_SIZE, 90).catch(error => {
 console.log('Failed to preload full-size image:', error);
    });
  }
}
function initializeLazyLoading() {
  const lazyImages = document.querySelectorAll('.lazy-load');
  if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          loadLazyImage(img);
          observer.unobserve(img);
        }
      });
    }, {
      rootMargin: '50px 0px',
      threshold: 0.1
    });
    lazyImages.forEach(img => imageObserver.observe(img));
  } else {
    lazyImages.forEach(img => loadLazyImage(img));
  }
}
async function loadLazyImage(img) {
  const dataSrc = img.dataset.src;
  const index = img.dataset.index;
  const isThumbnail = img.classList.contains('image-preview');
  if (!dataSrc) return;
  try {
    const size = isThumbnail ? THUMBNAIL_SIZE : MEDIUM_SIZE;
    const quality = isThumbnail ? 75 : 85;
    const optimizedSrc = dataSrc.includes('&size=') ? dataSrc :
      `${dataSrc}${dataSrc.includes('?') ? '&' : '?'}size=${size}&quality=${quality}`;
    const cacheKey = `${dataSrc}_${size}_${quality}`;
    const cached = imageCache.get(cacheKey);
    if (cached && (Date.now() - cached.timestamp) < IMAGE_CACHE_EXPIRY) {
      img.src = cached.url;
      img.classList.add('loaded');
      hidePlaceholder(img);
      return;
    }
    const imgElement = new Image();
    imgElement.onload = () => {
      img.src = optimizedSrc;
      img.classList.add('loaded');
      hidePlaceholder(img);
      imageCache.set(cacheKey, {
        url: optimizedSrc,
        timestamp: Date.now(),
        size: size,
        quality: quality
      });
    };
    imgElement.onerror = () => {
      showImageError(img);
    };
    imgElement.src = optimizedSrc;
  } catch (error) {
 console.error('Error loading lazy image:', error);
    showImageError(img);
  }
}
function hidePlaceholder(img) {
  const placeholder = img.nextElementSibling;
  if (placeholder && placeholder.classList.contains('image-placeholder')) {
    placeholder.style.opacity = '0';
    setTimeout(() => {
      placeholder.style.display = 'none';
    }, 300);
  }
}
function showImageError(img) {
  const placeholder = img.nextElementSibling;
  if (placeholder && placeholder.classList.contains('image-placeholder')) {
    placeholder.innerHTML = `
      <div class="error-icon"><i class="fas fa-exclamation-triangle"></i></div>
      <div class="loading-text">Failed to load</div>
    `;
    placeholder.classList.add('error');
  }
}

runBtn.addEventListener("click", function () {
  if (runBtn.classList.contains("running")) {
    if (controller) {
      controller.abort();
    }

    fetch("/stop/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ request_id: runRequest }),
    });

    runBtn.textContent = "Run";
    runBtn.classList.remove("running");
    statusDiv.textContent = "Stopped by user.";
    setTimeout(() => {
 console.log('Refreshing run folders after manual stop...');
      loadAllRunFolders();
    }, 1000);
    return;
  }

  const template = document.getElementById("templateOption").value;

  const name = document.getElementById("name").value.trim();
  const name2 = document.getElementById("name2").value.trim();
  if (!name && !name2) {
    statusDiv.textContent =
      "Please enter at least one name before starting the scan.";
    return;
  }

  for (let i = 1; i <= 6; i++) {
    const site = document.getElementById(`site${i}`).value.trim();
    const type = document.getElementById(`type${i}`).value;
    const time = document.getElementById(`time${i}`).value;

    if (!site || !/^\d{1,4}$/.test(site)) {
      statusDiv.textContent = `Sample ${i}: Site must be 1-4 digits only.`;
      return;
    }

    if (!type || !time) {
      statusDiv.textContent = `Please fill in all fields for Sample ${i}.`;
      return;
    }
  }

  runBtn.textContent = "Stop";
  runBtn.classList.add("running");
  statusDiv.textContent = "Running scan...";

  controller = new AbortController();

  const payload = {
    name: name,
    name2: name2,
    template: template,
    samples: Array.from({ length: 6 }, (_, i) => {
      const idx = i + 1;
      const site = document.getElementById(`site${idx}`).value.trim();
      const type = document.getElementById(`type${idx}`).value;
      const time = document.getElementById(`time${idx}`).value;
      const year = "2025";
      return `${idx}_${site}-${year}-${type}-${time}`;
    }),
  };

  fetch("/run/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
    signal: controller.signal,
  })
    .then((res) => res.json())
    .then((data) => {
      runRequest = data.request_id || null;
statusDiv.textContent =
  data.status === "success" ? "Scan complete." : (data.message || "Scan failed.");

    })
    .catch((err) => {
      if (err.name === "AbortError") {
        statusDiv.textContent = "Scan aborted.";
      } else {
        statusDiv.textContent = "Request failed: " + err;
      }
    })
    .finally(() => {
      runBtn.textContent = "Run";
      runBtn.classList.remove("running");
      controller = null;
      setTimeout(() => {
 console.log('Refreshing run folders after scan completion...');
        loadAllRunFolders();
      }, 2000);
    });
});


for (let i = 1; i <= 6; i++) {
  const input = document.getElementById(`site${i}`);
  input.addEventListener("input", function () {
    this.value = this.value.replace(/\D/g, "").slice(0, 4);
  });
}

document
  .getElementById("scanForm")
  .addEventListener("submit", (e) => e.preventDefault());

function retakeSample() {
  const retakeBtn = document.getElementById("retakeButton");
  const statusDiv = document.getElementById("status");
  
  if (!retakeBtn) {
    console.error("Retake button not found!");
    return;
  }
  
  if (retakeBtn.classList.contains("running")) {
    fetch("/stop-retake/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    })
    .then((res) => res.json())
    .then((data) => {
      retakeBtn.innerHTML = '<i class="fas fa-redo"></i> Retake Selected Dish';
      retakeBtn.classList.remove("running");
      statusDiv.textContent = data.status === "success" 
        ? "Retake stopped by user."
        : `Error: ${data.message}`;
      setTimeout(() => {
        console.log('Refreshing run folders after retake stop...');
        loadAllRunFolders();
      }, 1000);
    })
    .catch((err) => {
      statusDiv.textContent = "Request failed: " + err;
    });
    return;
  }

  const sample = document.getElementById("retake-sample").value.trim();
  if (!sample || isNaN(sample) || sample < 1 || sample > 6) {
    alert("Please enter a valid sample number between 1 and 6.");
    return;
  }

  retakeBtn.innerHTML = '<i class="fas fa-stop"></i> Stop Retake';
  retakeBtn.classList.add("running");
  console.log("Retake button updated - innerHTML:", retakeBtn.innerHTML, "has running class:", retakeBtn.classList.contains("running"));
  
  if (!retakeBtn.classList.contains("running")) {
    console.error("Failed to add running class to retake button!");
  }
  
  statusDiv.textContent = `Retaking dish ${sample}...`;

  fetch("/retake-sample/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample: sample }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "success") {
        statusDiv.textContent = `Retake started for dish ${sample}.`;
        setTimeout(() => {
          console.log('Refreshing run folders after retake completion...');
          loadAllRunFolders();
        }, 2000);
      } else {
        statusDiv.textContent = `Error: ${data.message}`;
        retakeBtn.innerHTML = '<i class="fas fa-redo"></i> Retake Selected Dish';
        retakeBtn.classList.remove("running");
      }
    })
    .catch((err) => {
      console.error("Retake request failed:", err);
      statusDiv.textContent = "Request failed: " + err;
      retakeBtn.innerHTML = '<i class="fas fa-redo"></i> Retake Selected Dish';
      retakeBtn.classList.remove("running");
    });
}

async function checkStitchingStatus(runFolder) {
  try {
    const response = await fetch(`/check-stitching-status/?run_folder=${runFolder}`);
    const result = await response.json();
    if (result.status === 'success') {
      const indicator = document.getElementById('stitching-status-indicator');
      if (indicator) {
        if (result.is_stitched) {
          indicator.style.display = 'block';
 console.log(`Run ${runFolder} is fully stitched`);
        } else {
          indicator.style.display = 'none';
 console.log(`Run ${runFolder} is not yet fully stitched (${result.stitched_subfolders}/${result.total_subfolders} folders)`);
        }
      }
      const modalIndicator = document.getElementById('modal-stitching-status-indicator');
      if (modalIndicator) {
        if (result.is_stitched) {
          modalIndicator.style.display = 'block';
        } else {
          modalIndicator.style.display = 'none';
        }
      }
    }
  } catch (error) {
 console.error('Error checking stitching status:', error);
  }
}

async function loadRunInfo(runFolder = null) {
 console.log('loadRunInfo called with:', runFolder);
  const runFolderSpan = document.getElementById('run-folder-name');
  const subfolderCountSpan = document.getElementById('subfolder-count');
  if (!runFolderSpan) {
 console.error('run-folder-name element not found');
    return;
  }
  try {
    const url = runFolder ? `/get-run-subfolders/?run_folder=${runFolder}` : '/get-run-subfolders/';
 console.log('Making request to:', url);
    const response = await fetch(url);
 console.log('Response received:', response);
    const result = await response.json();
 console.log('Result:', result);
    if (result.status === 'success') {
      runFolderSpan.textContent = result.run_folder;
      await checkStitchingStatus(result.run_folder);
      if (subfolderCountSpan) {
        subfolderCountSpan.textContent = result.total_subfolders || 0;
      }
    } else {
      runFolderSpan.textContent = `Error: ${result.message}`;
      if (subfolderCountSpan) {
        subfolderCountSpan.textContent = '0';
      }
 console.log('API Error:', result.message);
    }
  } catch (error) {
 console.error('loadRunInfo error:', error);
    runFolderSpan.textContent = 'Error loading run info';
    if (subfolderCountSpan) {
      subfolderCountSpan.textContent = '0';
    }
  }
}

function onRunFolderChange() {
  const select = document.getElementById('run-folder-select');
  const selectedRun = select.value;
 console.log('Run folder changed to:', selectedRun);
  if (selectedRun) {
    loadRunInfo(selectedRun);
  }
}


function showConfirmationModal(runFolder = null) {
  const modal = document.getElementById('confirmationModal');
  if (runFolder) {
    const runNumberElement = document.getElementById('modal-run-number');
    const runNumberValue = document.getElementById('modal-run-number-value');
    if (runNumberElement && runNumberValue) {
      runNumberValue.textContent = runFolder;
      runNumberElement.style.display = 'inline-block';
    }
  }
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
  const confirmBtn = document.getElementById('confirm-stitching-btn');
  if (confirmBtn) {
    confirmBtn.removeEventListener('click', handleConfirmClick);
    confirmBtn.addEventListener('click', handleConfirmClick);
  }
  requestAnimationFrame(() => {
    const content = modal.querySelector('.modal-content');
    content.style.animation = 'modalFadeIn 0.3s ease-out';
  });
}

function closeConfirmationModal() {
  const modal = document.getElementById('confirmationModal');
  modal.classList.remove('show');
  document.body.style.overflow = 'auto';
 console.log('Modal closed');
}

function showStitchedWarningModal() {
  const confirmationModal = document.getElementById('confirmationModal');
  confirmationModal.style.display = 'none';
  const confirmBtn = document.getElementById('confirm-stitching-btn');
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.style.pointerEvents = 'none';
  }
  const modal = document.getElementById('stitchedWarningModal');
 console.log('Modal element found:', modal);
 console.log('Modal classes before:', modal.className);
 console.log('Modal style before:', modal.style.cssText);
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
  const proceedBtn = document.getElementById('proceed-stitching-btn');
  if (proceedBtn) {
 console.log('Setting up proceed button event listener');
    proceedBtn.removeEventListener('click', handleProceedClick);
    proceedBtn.addEventListener('click', handleProceedClick);
  } else {
 console.error(' Proceed button not found!');
  }
 console.log('Modal classes after:', modal.className);
 console.log('Modal style after:', modal.style.cssText);
 console.log('Stitched warning modal shown');
}
function handleProceedClick(e) {
  e.preventDefault();
  e.stopPropagation();
 console.log('Proceed Anyway addEventListener triggered!');
 console.log('Event target:', e.target);
 console.log('Current target:', e.currentTarget);
 console.log('Proceed Anyway clicked - user wants to stitch already stitched run');
  closeStitchedWarningModal(false);
  closeConfirmationModal();
  proceedWithStitching();
}

function closeStitchedWarningModal(restoreConfirmationModal = true) {
  const modal = document.getElementById('stitchedWarningModal');
  modal.classList.remove('show');
  document.body.style.overflow = 'auto';
  if (restoreConfirmationModal) {
    const confirmationModal = document.getElementById('confirmationModal');
    confirmationModal.style.display = '';
    const confirmBtn = document.getElementById('confirm-stitching-btn');
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.style.pointerEvents = '';
    }
  }
 console.log('Stitched warning modal closed');
}

function handleConfirmClick(e) {
 console.log('handleConfirmClick called!');
  e.preventDefault();
  e.stopPropagation();
  confirmStitching();
}

async function confirmStitching() {
 console.log('confirmStitching() called');
 console.log('Debug before closing modal:');
 console.log('- window.modalSubfolders:', window.modalSubfolders);
 console.log('- window.totalSelectableItems:', window.totalSelectableItems);
 console.log('- Selected folders count:', getSelectedFolderCount());
  if (!window.modalSubfolders || window.modalSubfolders.length === 0) {
 console.error(' No modal subfolders data! Cannot proceed with stitching.');
    alert('Error: Modal data not properly loaded. Please try clicking "Stitch Images" again.');
    return;
  }
  if (typeof window.totalSelectableItems === 'undefined') {
 console.error(' No totalSelectableItems! Cannot proceed with stitching.');
    alert('Error: Modal data not properly loaded. Please try clicking "Stitch Images" again.');
    return;
  }
  const selectedRun = document.getElementById('run-folder-select').value;
 console.log('Selected run:', selectedRun);
  if (selectedRun) {
    const modalIndicator = document.getElementById('modal-stitching-status-indicator');
    const isAlreadyKnownStitched = modalIndicator && modalIndicator.style.display === 'block';
    if (isAlreadyKnownStitched) {
 console.log('Run is already known to be stitched, showing warning immediately');
      showStitchedWarningModal();
    } else {
 console.log('Checking stitching status for:', selectedRun);
      await checkRunStitchingStatus(selectedRun);
    }
  } else {
 console.log('No run selected, proceeding normally');
    proceedWithStitching();
  }
}

async function checkRunStitchingStatus(runFolder) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    const response = await fetch(`/check-stitching-status/?run_folder=${runFolder}`, {
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    const result = await response.json();
    if (result.status === 'success' && result.is_stitched) {
 console.log(`Run ${runFolder} is already stitched, showing warning`);
      showStitchedWarningModal();
    } else {
 console.log(`Run ${runFolder} is not stitched, proceeding normally`);
      proceedWithStitching();
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('Stitching status check timed out, proceeding normally');
    } else {
 console.error('Error checking stitching status:', error);
    }
    proceedWithStitching();
  }
}

function proceedWithStitching() {
  closeStitchedWarningModal();
  closeConfirmationModal();
 console.log('User confirmed, starting process');
  setTimeout(() => {
 console.log('Calling startStitchingProcess()...');
 console.log('Post-modal data check:');
 console.log('- window.modalSubfolders still exists:',!!window.modalSubfolders);
 console.log('- window.totalSelectableItems still exists:', typeof window.totalSelectableItems!== 'undefined');
    startStitchingProcess();
  }, 100);
}

document.getElementById('confirmationModal').addEventListener('click', function(e) {
  if (e.target === this) {
    closeConfirmationModal();
  }
});

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    const modal = document.getElementById('confirmationModal');
    if (modal.classList.contains('show')) {
      closeConfirmationModal();
    }
  }
});

async function handleStitchImages() {
 console.log('handleStitchImages called');
  const button = document.getElementById('uploadToStitcher');
  const originalButtonText = button.innerHTML;
  try {
    const selectedRun = document.getElementById('run-folder-select').value;
 console.log('Selected run folder:', selectedRun);
    button.disabled = true;
    button.innerHTML = '<div class="loading"></div> Loading folders...';
    const startTime = performance.now();
    const infoResult = await getCachedFolderData(selectedRun);
    const fetchTime = performance.now() - startTime;
 console.log(`Folder data retrieved in ${fetchTime.toFixed(2)}ms:`, infoResult);
    if (infoResult.status !== 'success') {
      alert('Error: ' + (infoResult.message || 'Failed to get folder information'));
      return;
    }
    button.innerHTML = '<div class="loading"></div> Preparing modal...';
    const populateStartTime = performance.now();
    populateModalWithFolders(infoResult.subfolders);
    const populateTime = performance.now() - populateStartTime;
 console.log(`Modal populated in ${populateTime.toFixed(2)}ms`);
    showConfirmationModal(selectedRun);
  } catch (error) {
 console.error('Error loading subfolder info:', error);
    alert('Error loading folder information: ' + error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = originalButtonText;
  }
}

function populateModalWithFolders(subfolders) {
  const folderSelection = document.getElementById('folder-selection');
  let checkboxHtml = '';
  let folderIndex = 0;
  const foldersWithRetakes = new Set();
  subfolders.forEach((subfolder) => {
    if (subfolder.has_nested && subfolder.nested_folders && subfolder.nested_folders.length > 0) {
      foldersWithRetakes.add(subfolder.name);
    }
  });
  subfolders.forEach((subfolder, parentIndex) => {
    const folderName = subfolder.name;
    const mainImageCount = subfolder.image_count;
    const hasNested = subfolder.has_nested;
    const nestedFolders = subfolder.nested_folders || [];
    const shouldSelectMain = !hasNested || nestedFolders.length === 0;
    const parentClass = hasNested ? 'parent-folder' : '';
    checkboxHtml += `
      <div class="folder-item ${parentClass}" onclick="toggleFolderCheckbox(${folderIndex})">
        <input type="checkbox"
               id="folder-checkbox-${folderIndex}"
               class="folder-checkbox"
               ${shouldSelectMain ? 'checked' : ''}
               data-folder-type="main"
               data-parent-index="${parentIndex}"
               data-nested-index="-1"
               onclick="event.stopPropagation()">
        <div class="folder-info">
          <div class="folder-name">
            ${folderName}
            ${hasNested ? '<span class="expand-toggle">(+ retakes)</span>' : ''}
          </div>
          <div class="folder-details">${mainImageCount} images (main folder)</div>
        </div>
      </div>
    `;
    folderIndex++;
    if (hasNested && nestedFolders.length > 0) {
      checkboxHtml += '<div class="nested-folder">';
      let mostRecentRetake = null;
      let mostRecentTimestamp = null;
      nestedFolders.forEach((nestedFolder) => {
        let timestamp = null;
        const fullTimestampMatch = nestedFolder.name.match(/(\d{8}_\d{6})$/);
        if (fullTimestampMatch) {
          timestamp = fullTimestampMatch[1];
        } else {
          const splitTimestampMatch = nestedFolder.name.match(/_split_\d+_(\d{8}_\d{6})$/);
          if (splitTimestampMatch) {
            timestamp = splitTimestampMatch[1];
          } else {
            const timeMatch = nestedFolder.name.match(/(\d{6})$/);
            if (timeMatch) {
              const today = new Date();
              const dateStr = today.getFullYear().toString() +
                            (today.getMonth() + 1).toString().padStart(2, '0') +
                            today.getDate().toString().padStart(2, '0');
              timestamp = dateStr + '_' + timeMatch[1];
            }
          }
        }
        if (timestamp && (!mostRecentTimestamp || timestamp > mostRecentTimestamp)) {
          mostRecentTimestamp = timestamp;
          mostRecentRetake = nestedFolder;
        }
      });
      nestedFolders.forEach((nestedFolder, nestedIndex) => {
        const shouldSelectNested = nestedFolder === mostRecentRetake;
        checkboxHtml += `
          <div class="folder-item" onclick="toggleFolderCheckbox(${folderIndex})">
            <input type="checkbox"
                   id="folder-checkbox-${folderIndex}"
                   class="folder-checkbox"
                   ${shouldSelectNested ? 'checked' : ''}
                   data-folder-type="nested"
                   data-parent-index="${parentIndex}"
                   data-nested-index="${nestedIndex}"
                   onclick="event.stopPropagation()">
            <div class="folder-info">
              <div class="folder-name">${nestedFolder.name}</div>
              <div class="folder-details">${nestedFolder.image_count} images (retake/nested)</div>
            </div>
          </div>
        `;
        folderIndex++;
      });
      checkboxHtml += '</div>';
    }
  });
  folderSelection.innerHTML = checkboxHtml;
 console.log('Modal HTML populated:');
 console.log('- Checkbox HTML length:', checkboxHtml.length);
 console.log('- Checkboxes in DOM after population:', document.querySelectorAll('[id^="folder-checkbox-"]').length);
  window.modalSubfolders = subfolders;
  window.totalSelectableItems = folderIndex;
 console.log('Modal data stored:');
 console.log('- window.modalSubfolders:', window.modalSubfolders);
 console.log('- window.totalSelectableItems:', window.totalSelectableItems);
 console.log('- Total checkboxes created:', folderIndex);
  window.testModalData = function() {
 console.log('Testing modal data:');
 console.log('- window.modalSubfolders exists:',!!window.modalSubfolders);
 console.log('- window.totalSelectableItems exists:', typeof window.totalSelectableItems!== 'undefined');
 console.log('- Checkboxes in DOM:', document.querySelectorAll('[id^="folder-checkbox-"]').length);
 console.log('- Checked checkboxes:', document.querySelectorAll('[id^="folder-checkbox-"]:checked').length);
    for (let i = 0; i < window.totalSelectableItems; i++) {
      const checkbox = document.getElementById(`folder-checkbox-${i}`);
      if (checkbox) {
 console.log(`- Checkbox ${i}: checked=${checkbox.checked}, type=${checkbox.getAttribute('data-folder-type')}`);
      }
    }
  };
  updateSelectionCounter();
}

function toggleFolderCheckbox(index) {
  const checkbox = document.getElementById(`folder-checkbox-${index}`);
  const currentChecked = checkbox.checked;
  const selectedCount = getSelectedFolderCount();
  if (!currentChecked && selectedCount >= 6) {
    showSelectionLimitMessage();
    return;
  }
  if (currentChecked) {
    showUncheckConfirmation(() => {
      checkbox.checked = false;
      updateSelectionCounter();
    });
    return;
  }
  checkbox.checked = true;
  updateSelectionCounter();
}

function getSelectedFolderCount() {
  let count = 0;
  for (let checkboxIndex = 0; checkboxIndex < window.totalSelectableItems; checkboxIndex++) {
    const checkbox = document.getElementById(`folder-checkbox-${checkboxIndex}`);
    if (checkbox && checkbox.checked) {
      count++;
    }
  }
  return count;
}

function updateSelectionCounter() {
  const selectedCount = getSelectedFolderCount();
  const maxSelections = 6;
  let counter = document.getElementById('selection-counter');
  if (!counter) {
    counter = document.createElement('div');
    counter.id = 'selection-counter';
    counter.style.cssText = `
      text-align: center;
      margin: 10px 0;
      padding: 8px;
      background: linear-gradient(135deg, #f8f9ff, #e3e8ef);
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      border: 1px solid rgba(74, 124, 89, 0.2);
    `;
    const folderSelection = document.getElementById('folder-selection');
    folderSelection.parentNode.insertBefore(counter, folderSelection.nextSibling);
  }
  const remaining = maxSelections - selectedCount;
  if (selectedCount === 0) {
    counter.innerHTML = `Select up to ${maxSelections} folders for stitching`;
    counter.style.color = '#6c757d';
  } else if (remaining > 0) {
    counter.innerHTML = `${selectedCount} selected, ${remaining} remaining (max ${maxSelections})`;
    counter.style.color = '#4a7c59';
  } else {
    counter.innerHTML = `${selectedCount}/${maxSelections} folders selected (maximum reached)`;
    counter.style.color = '#2d5016';
  }
}

function showSelectionLimitMessage() {
  let limitMessage = document.getElementById('selection-limit-message');
  if (!limitMessage) {
    limitMessage = document.createElement('div');
    limitMessage.id = 'selection-limit-message';
    limitMessage.style.cssText = `
      text-align: center;
      margin: 10px 0;
      padding: 12px;
      background: linear-gradient(135deg, #fff3cd, #ffeaa7);
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      color: #856404;
      border: 1px solid #ffeaa7;
      animation: pulse 0.5s ease-in-out;
    `;
    const counter = document.getElementById('selection-counter');
    counter.parentNode.insertBefore(limitMessage, counter.nextSibling);
  }
  limitMessage.innerHTML = `Maximum of 6 folders can be selected for stitching`;
  setTimeout(() => {
    if (limitMessage) {
      limitMessage.style.opacity = '0';
      setTimeout(() => {
        if (limitMessage && limitMessage.parentNode) {
          limitMessage.parentNode.removeChild(limitMessage);
        }
      }, 300);
    }
  }, 3000);
}

function showUncheckConfirmation(callback) {
  const overlay = document.createElement('div');
  overlay.id = 'uncheck-confirmation-overlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(8px);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 2000;
    opacity: 0;
    visibility: hidden;
    transition: all 0.3s ease;
  `;
  const modalContent = document.createElement('div');
  modalContent.style.cssText = `
    background: rgba(255, 255, 255, 0.98);
    backdrop-filter: blur(20px);
    border-radius: 24px;
    padding: 40px;
    max-width: 500px;
    width: 90%;
    box-shadow:
      0 20px 60px rgba(0, 0, 0, 0.3),
      0 8px 32px rgba(74, 124, 89, 0.2);
    border: 2px solid rgba(255, 255, 255, 0.3);
    transform: scale(0.9) translateY(20px);
    transition: all 0.3s ease;
    text-align: center;
  `;
  modalContent.innerHTML = `
    <div style="
      font-size: 64px;
      font-weight: 900;
      margin-bottom: 20px;
      width: 80px;
      height: 80px;
      border-radius: 50%;
      background: linear-gradient(135deg, #ffc107, #e0a800);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 20px;
      box-shadow: 0 8px 25px rgba(255, 193, 7, 0.3);
      text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
    ">?</div>
    <h2 style="
      font-size: 24px;
      font-weight: 700;
      color: #2c3e50;
      margin-bottom: 15px;
      background: linear-gradient(135deg, #2d5016, #4a7c59);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    ">Are you sure you want to uncheck?</h2>
    <div style="
      font-size: 16px;
      color: #34495e;
      line-height: 1.6;
      margin-bottom: 30px;
      padding: 20px;
      background: linear-gradient(135deg, #f8f9ff, #e3e8ef);
      border-radius: 12px;
      border-left: 4px solid #4a7c59;
    ">
      <strong>Auto selection was already applied to most recent retake and main folders (default)</strong>
    </div>
    <div style="display: flex; gap: 15px; justify-content: center;">
      <button id="confirm-uncheck-btn" style="
        padding: 14px 30px;
        font-size: 16px;
        font-weight: 600;
        border: none;
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        min-width: 120px;
        background: linear-gradient(135deg, #dc3545, #c82333);
        color: white;
        box-shadow: 0 4px 15px rgba(220, 53, 69, 0.3);
      ">Yes, Uncheck</button>
      <button id="cancel-uncheck-btn" style="
        padding: 14px 30px;
        font-size: 16px;
        font-weight: 600;
        border: none;
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.3s ease;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        min-width: 120px;
        background: linear-gradient(135deg, #4a7c59, #2d5016);
        color: white;
        box-shadow: 0 4px 15px rgba(74, 124, 89, 0.3);
      ">Cancel</button>
    </div>
  `;
  overlay.appendChild(modalContent);
  document.body.appendChild(overlay);
  setTimeout(() => {
    overlay.style.opacity = '1';
    overlay.style.visibility = 'visible';
    modalContent.style.transform = 'scale(1) translateY(0)';
  }, 50);
  document.getElementById('confirm-uncheck-btn').addEventListener('click', () => {
    closeUncheckConfirmation();
    callback();
  });
  document.getElementById('cancel-uncheck-btn').addEventListener('click', () => {
    closeUncheckConfirmation();
  });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      closeUncheckConfirmation();
    }
  });
  const escapeHandler = (e) => {
    if (e.key === 'Escape') {
      closeUncheckConfirmation();
      document.removeEventListener('keydown', escapeHandler);
    }
  };
  document.addEventListener('keydown', escapeHandler);
  function closeUncheckConfirmation() {
    overlay.style.opacity = '0';
    overlay.style.visibility = 'hidden';
    setTimeout(() => {
      if (overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
      }
    }, 300);
  }
}

async function startStitchingProcess() {
  if (stitchingInProgress) {
 console.log('Stitching already in progress, ignoring duplicate call');
    return;
  }
  stitchingInProgress = true;
 console.log('startStitchingProcess() called');
  const button = document.getElementById('uploadToStitcher');
  const statusDiv = document.getElementById('stitcher-status');
 console.log('Debug info:');
 console.log('- window.modalSubfolders:', window.modalSubfolders);
 console.log('- window.totalSelectableItems:', window.totalSelectableItems);
 console.log('- button:', button);
 console.log('- statusDiv:', statusDiv);
 console.log('Additional debug info:');
 console.log('- typeof window.modalSubfolders:', typeof window.modalSubfolders);
 console.log('- typeof window.totalSelectableItems:', typeof window.totalSelectableItems);
 console.log('- window.modalSubfolders length:', window.modalSubfolders? window.modalSubfolders.length: 'undefined');
 console.log('- All checkboxes in DOM:', document.querySelectorAll('[id^="folder-checkbox-"]').length);
  const selectedFolders = [];
  let allSubfolders = window.modalSubfolders || [];
  if (!allSubfolders || allSubfolders.length === 0) {
 console.error(' window.modalSubfolders is missing!');
 console.error(' Attempting to recover subfolder data...');
    const selectedRun = document.getElementById('run-folder-select').value;
    if (selectedRun) {
      try {
 console.log('Fetching fresh subfolder data for recovery...');
        const response = await fetch(`/get-run-subfolders/?run_folder=${selectedRun}`);
        const result = await response.json();
        if (result.status === 'success') {
          allSubfolders = result.subfolders;
          window.modalSubfolders = allSubfolders;
 console.log('Recovered subfolder data:', allSubfolders);
        }
      } catch (error) {
 console.error(' Failed to recover subfolder data:', error);
      }
    }
  }
  if (typeof window.totalSelectableItems === 'undefined') {
 console.error(' window.totalSelectableItems is undefined!');
 console.error(' Attempting to recover modal data...');
    const checkboxesInDOM = document.querySelectorAll('[id^="folder-checkbox-"]').length;
    if (checkboxesInDOM > 0) {
 console.log('Recovered totalSelectableItems from DOM:', checkboxesInDOM);
      window.totalSelectableItems = checkboxesInDOM;
    } else {
      alert('Error: Modal data not properly loaded. Please try again.');
      return;
    }
  }
 console.log('Starting checkbox iteration...');
  for (let checkboxIndex = 0; checkboxIndex < window.totalSelectableItems; checkboxIndex++) {
    const checkbox = document.getElementById(`folder-checkbox-${checkboxIndex}`);
 console.log(`- Checkbox ${checkboxIndex}:`, checkbox? 'found': 'NOT FOUND', checkbox? checkbox.checked: 'N/A');
    if (checkbox && checkbox.checked) {
      const folderType = checkbox.getAttribute('data-folder-type');
      const parentIndex = parseInt(checkbox.getAttribute('data-parent-index'));
      const nestedIndex = parseInt(checkbox.getAttribute('data-nested-index'));
 console.log(`- Selected checkbox ${checkboxIndex}: type=${folderType}, parent=${parentIndex}, nested=${nestedIndex}`);
      if (folderType === 'main') {
        const subfolder = allSubfolders[parentIndex];
 console.log(`- Adding main folder:`, subfolder);
        selectedFolders.push({
          ...subfolder,
          originalIndex: parentIndex,
          isNested: false,
          displayName: subfolder.name,
          folderPath: subfolder.path
        });
      } else if (folderType === 'nested') {
        const parentFolder = allSubfolders[parentIndex];
        const nestedFolder = parentFolder.nested_folders[nestedIndex];
 console.log(`- Adding nested folder:`, nestedFolder);
        selectedFolders.push({
          name: nestedFolder.name,
          path: nestedFolder.path,
          image_count: nestedFolder.image_count,
          originalIndex: parentIndex,
          nestedIndex: nestedIndex,
          isNested: true,
          displayName: `${parentFolder.name} > ${nestedFolder.name}`,
          folderPath: nestedFolder.path
        });
      }
    }
  }
 console.log('Selected folders:', selectedFolders);
  if (selectedFolders.length === 0) {
 console.warn(' No folders selected');
    alert('Please select at least one folder to upload.');
    return;
  }
  if (selectedFolders.length > 6) {
 console.warn(' Too many folders selected:', selectedFolders.length);
    alert('Maximum of 6 folders can be selected for stitching. Please deselect some folders.');
    return;
  }
 console.log('Proceeding with', selectedFolders.length, 'selected folders');

  const selectedRun = document.getElementById('run-folder-select').value;

  saveStitcherState({
    isProcessing: true,
    selectedFolders: selectedFolders,
    selectedRun: selectedRun,
    totalFolders: selectedFolders.length
  });

  saveStitcherProgress({
    completedCount: 0,
    successCount: 0,
    failCount: 0,
    results: []
  });
  button.disabled = true;
  button.innerHTML = '<div class="loading"></div> Processing...';
  const statusMessage = `<span style="color: #4a7c59;">UPLOAD: Starting uploads for ${selectedFolders.length} selected folders...</span>`;
  statusDiv.innerHTML = statusMessage;
 console.log('Status updated:', statusMessage);
 console.log('Button state:', {
    disabled: button.disabled,
    innerHTML: button.innerHTML,
    statusDivContent: statusDiv.innerHTML
  });
  try {
    const subfolders = selectedFolders;
    let successCount = 0;
    let failCount = 0;
    const results = [];
    for (let i = 0; i < subfolders.length; i++) {
      const subfolder = subfolders[i];
 console.log(`Uploading folder ${i + 1}/${subfolders.length}: ${subfolder.displayName}`);
      statusDiv.innerHTML = `
        <div style="color: #4a7c59;">
          UPLOAD: Uploading folder ${i + 1}/${subfolders.length}: ${subfolder.displayName}
        </div>
        <div style="color: #6c757d; font-size: 12px; margin-top: 5px;">
          Completed: ${i}/${subfolders.length} | Success: ${successCount} | Failed: ${failCount}
        </div>
      `;
      try {
        const uploadData = {
          confidence_threshold: 0.6,
          subfolder_index: subfolder.originalIndex,
          run_folder: selectedRun,
          image_rotations: imageRotations
        };
        if (subfolder.isNested) {
          uploadData.nested_index = subfolder.nestedIndex;
        }
 console.log('Making API request to /upload-to-stitcher/');
 console.log('Request data:', uploadData);
 console.log('CSRF Token:', getCsrfToken());
        const response = await fetch('/upload-to-stitcher/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
          },
          body: JSON.stringify(uploadData)
        });
 console.log('Response status:', response.status);
 console.log('Response headers:', [...response.headers.entries()]);
        const result = await response.json();
 console.log(`Upload result for ${subfolder.name}:`, result);
        if (result.status === 'success') {
          successCount++;
          let guid = 'N/A';
          if (result.stitcher_response) {
            if (result.stitcher_response.guid) {
              guid = result.stitcher_response.guid;
            } else if (result.stitcher_response.zip_message) {
              const match = result.stitcher_response.zip_message.match(/\/media\/([a-f0-9-]{36})/);
              if (match) {
                guid = match[1];
              }
            }
          }
 console.log(`Extracted GUID for ${subfolder.name}: ${guid}`);
          results.push({
            folder: subfolder.displayName,
            status: 'success',
            guid: guid
          });
        } else {
          failCount++;
          results.push({
            folder: subfolder.displayName,
            status: 'error',
            error: result.message
          });
        }
      } catch (error) {
 console.error(`Upload error for ${subfolder.name}:`, error);
        failCount++;
        results.push({
          folder: subfolder.displayName,
          status: 'error',
          error: error.message
        });
      }

      saveStitcherProgress({
        completedCount: i + 1,
        successCount: successCount,
        failCount: failCount,
        results: results
      });
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    displayFinalResults(successCount, failCount, results);
    clearStitcherState();
  } catch (error) {
 console.error('Process failed:', error);
    statusDiv.innerHTML = `<span style="color: #dc3545;">ERROR: Process failed: ${error.message}</span>`;
    clearStitcherState();
  } finally {
    button.disabled = false;
    button.innerHTML = 'Stitch Images';
    stitchingInProgress = false;
 console.log('Stitching protection reset, ready for next process');
  }
}

function saveStitcherState(state) {
  localStorage.setItem(STITCHER_STATE_KEY, JSON.stringify({
    ...state,
    timestamp: Date.now()
  }));
}

function getStitcherState() {
  try {
    const stored = localStorage.getItem(STITCHER_STATE_KEY);
    if (stored) {
      const state = JSON.parse(stored);
      if (Date.now() - state.timestamp > 3600000) {
        clearStitcherState();
        return null;
      }
      return state;
    }
  } catch (error) {
 console.error('Error reading stitcher state:', error);
  }
  return null;
}

function clearStitcherState() {
  localStorage.removeItem(STITCHER_STATE_KEY);
  localStorage.removeItem(STITCHER_PROGRESS_KEY);
  stitchingInProgress = false;
 console.log('Stitching protection reset due to state clear');
}

function saveStitcherProgress(progress) {
  localStorage.setItem(STITCHER_PROGRESS_KEY, JSON.stringify(progress));
}

function getStitcherProgress() {
  try {
    const stored = localStorage.getItem(STITCHER_PROGRESS_KEY);
    return stored ? JSON.parse(stored) : null;
  } catch (error) {
 console.error('Error reading stitcher progress:', error);
    return null;
  }
}

function restoreStitcherState() {
  const state = getStitcherState();
  const progress = getStitcherProgress();
  if (state && state.isProcessing) {
    const button = document.getElementById('uploadToStitcher');
    const statusDiv = document.getElementById('stitcher-status');
 console.log('Restoring stitcher state:', state);
    button.disabled = true;
    button.innerHTML = '<div class="loading"></div> Resuming...';
    statusDiv.innerHTML = `
      <div style="color: #ffc107; margin-bottom: 10px;">
        <strong>Process Recovery:</strong> Detected interrupted stitching process
      </div>
      <div style="color: #6c757d; font-size: 12px; margin-bottom: 10px;">
        Started: ${new Date(state.timestamp).toLocaleTimeString()}
      </div>
      <div style="color: #4a7c59;">
        Checking status and resuming from where we left off...
      </div>
    `;

    setTimeout(() => {
      resumeStitchingProcess(state, progress);
    }, 2000);
  }
}

async function resumeStitchingProcess(state, progress) {
  const button = document.getElementById('uploadToStitcher');
  const statusDiv = document.getElementById('stitcher-status');
  try {
 console.log('Resuming stitching process with state:', state);
    if (!state.selectedFolders || state.selectedFolders.length === 0) {
      throw new Error('No folder information found in saved state');
    }

    const totalFolders = state.selectedFolders.length;
    const startIndex = progress ? progress.completedCount : 0;
    let successCount = progress ? progress.successCount : 0;
    let failCount = progress ? progress.failCount : 0;
    const results = progress ? progress.results : [];

    statusDiv.innerHTML = `
      <div style="color: #4a7c59; margin-bottom: 10px;">
        <strong>Resuming Upload:</strong> Processing ${totalFolders - startIndex} remaining folders
      </div>
      <div style="color: #6c757d; font-size: 12px;">
        Completed: ${startIndex}/${totalFolders} | Success: ${successCount} | Failed: ${failCount}
      </div>
    `;

    for (let i = startIndex; i < state.selectedFolders.length; i++) {
      const subfolder = state.selectedFolders[i];
 console.log(`Processing folder ${i + 1}/${totalFolders}: ${subfolder.displayName}`);
      statusDiv.innerHTML = `
        <div style="color: #4a7c59;">
          UPLOAD: Processing folder ${i + 1}/${totalFolders}: ${subfolder.displayName}
        </div>
        <div style="color: #6c757d; font-size: 12px; margin-top: 5px;">
          Completed: ${i}/${totalFolders} | Success: ${successCount} | Failed: ${failCount}
        </div>
      `;

      try {
        const uploadData = {
          confidence_threshold: 0.6,
          subfolder_index: subfolder.originalIndex,
          run_folder: state.selectedRun,
          image_rotations: imageRotations
        };

        if (subfolder.isNested) {
          uploadData.nested_index = subfolder.nestedIndex;
        }

        const response = await fetch('/upload-to-stitcher/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
          },
          body: JSON.stringify(uploadData)
        });

        const result = await response.json();
        if (result.status === 'success') {
          successCount++;
          let guid = 'N/A';
          if (result.stitcher_response) {
            if (result.stitcher_response.guid) {
              guid = result.stitcher_response.guid;
            } else if (result.stitcher_response.zip_message) {
              const match = result.stitcher_response.zip_message.match(/\/media\/([a-f0-9-]{36})/);
              if (match) {
                guid = match[1];
              }
            }
          }
          results.push({
            folder: subfolder.displayName,
            status: 'success',
            guid: guid
          });
        } else {
          failCount++;
          results.push({
            folder: subfolder.displayName,
            status: 'error',
            error: result.message
          });
        }
      } catch (error) {
 console.error(`Upload error for ${subfolder.name}:`, error);
        failCount++;
        results.push({
          folder: subfolder.displayName,
          status: 'error',
          error: error.message
        });
      }

      saveStitcherProgress({
        completedCount: i + 1,
        successCount: successCount,
        failCount: failCount,
        results: results
      });

      await new Promise(resolve => setTimeout(resolve, 500));
    }

    displayFinalResults(successCount, failCount, results);
    clearStitcherState();

  } catch (error) {
 console.error('Resume process failed:', error);
    statusDiv.innerHTML = `
      <div style="color: #dc3545;">
        <strong><i class="fas fa-times"></i> Resume Failed:</strong> ${error.message}
      </div>
      <div style="color: #6c757d; font-size: 12px; margin-top: 5px;">
        You can try starting a new stitching process
      </div>
    `;
    clearStitcherState();
  } finally {
    button.disabled = false;
    button.innerHTML = 'Stitch Images';
  }
}

function displayFinalResults(successCount, failCount, results) {
  const statusDiv = document.getElementById('stitcher-status');
  let resultHtml = `
    <div style="color: #2c3e50; margin-bottom: 10px;">
      <strong>✅ Upload Complete:</strong> ${successCount} success, ${failCount} failed
    </div>
  `;

  results.forEach(result => {
    if (result.status === 'success') {
      const stitcherUrl = `http://10.147.19.124:3000/core/stitcher-form/${result.guid}`;
      resultHtml += `
        <div style="color: #22c55e; font-size: 12px; margin: 5px 0;">
          SUCCESS: <a href="${stitcherUrl}" 
                    target="_blank" 
                    style="color: #22c55e; text-decoration: none; border-bottom: 1px solid transparent; transition: border-bottom 0.3s ease;"
                    onmouseover="this.style.borderBottom='1px solid #22c55e'"
                    onmouseout="this.style.borderBottom='1px solid transparent'">
                    ${result.folder}
                  </a>
        </div>
      `;
    } else {
      resultHtml += `
        <div style="color: #dc3545; font-size: 12px; margin: 5px 0;">
          ERROR: ${result.folder} - Error: ${result.error}
        </div>
      `;
    }
  });

  statusDiv.innerHTML = resultHtml;
}

document.addEventListener('DOMContentLoaded', function() {
 console.log('DOMContentLoaded fired');
  loadRunInfo();
  setTimeout(loadAllRunFolders, 1000);
  setTimeout(() => {
    restoreStitcherState();
  }, 1000);
});

async function handlePreviewImages() {
 console.log('handlePreviewImages called');
  const button = document.getElementById('previewImages');
  const originalButtonText = button.innerHTML;
  try {
    const selectedRun = document.getElementById('run-folder-select').value;
 console.log('Selected run folder for preview:', selectedRun);
    if (!selectedRun) {
      alert('Please select a run folder first.');
      return;
    }
    button.disabled = true;
    button.innerHTML = '<div class="loading"></div> Loading preview...';
 console.log('Getting folder data for preview:', selectedRun);
    const startTime = performance.now();
    const result = await getCachedFolderData(selectedRun);
    const fetchTime = performance.now() - startTime;
 console.log(`Preview data fetched in ${fetchTime.toFixed(2)}ms:`, result);
    if (result.status !== 'success') {
      alert('Error: ' + (result.message || 'Failed to get folder information'));
      return;
    }
    currentPreviewData = {
      runFolder: selectedRun,
      subfolders: result.subfolders
    };
    const populateStartTime = performance.now();
    populateFolderSelector(result.subfolders);
    const populateTime = performance.now() - populateStartTime;
 console.log(`Folder selector populated in ${populateTime.toFixed(2)}ms`);
    showImagePreview(selectedRun);
    const stitchButton = document.getElementById('uploadToStitcher');
    if (stitchButton) {
      stitchButton.disabled = false;
      stitchButton.title = 'Click to start stitching process';
 console.log('Stitch Images button enabled after preview');
 console.log('Button state:', {
        disabled: stitchButton.disabled,
        onclick: stitchButton.onclick ? 'has onclick' : 'no onclick'
      });
    } else {
 console.error(' Stitch Images button not found!');
    }
  } catch (error) {
 console.error('Error loading preview info:', error);
    alert('Error loading folder information: ' + error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = originalButtonText;
  }
}

function populateFolderSelector(subfolders) {
  const selector = document.getElementById('folder-selector');
  if (!selector) {
 console.error('Folder selector element not found');
    return;
  }
  selector.innerHTML = '<option value="">Select a folder...</option>';
  if (!subfolders || subfolders.length === 0) {
    const emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = 'No folders available';
    emptyOption.disabled = true;
    selector.appendChild(emptyOption);
    return;
  }
  subfolders.forEach((subfolder, index) => {
    const mainOption = document.createElement('option');
    mainOption.value = `main-${index}`;
    mainOption.textContent = `${subfolder.name || 'Unknown'} (${subfolder.image_count || 0} images)`;
    selector.appendChild(mainOption);
    if (subfolder.nested_folders && subfolder.nested_folders.length > 0) {
      subfolder.nested_folders.forEach((nestedFolder, nestedIndex) => {
        const nestedOption = document.createElement('option');
        nestedOption.value = `nested-${index}-${nestedIndex}`;
        nestedOption.textContent = `  ${nestedFolder.name || 'Unknown'} (${nestedFolder.image_count || 0} images)`;
        selector.appendChild(nestedOption);
      });
    }
  });
  if (subfolders.length > 0) {
    selector.value = 'main-0';
    setTimeout(() => {
      loadFolderImages('main-0');
    }, 100);
  }
}

async function onFolderSelectionChange() {
  const selector = document.getElementById('folder-selector');
  const selectedValue = selector.value;
  if (selectedValue) {
    await loadFolderImages(selectedValue);
  } else {
    clearImageGrid();
  }
}

async function loadFolderImages(folderKey) {
  const imageGrid = document.getElementById('image-grid');
  if (!currentPreviewData || !currentPreviewData.subfolders) {
 console.error('No preview data available');
    imageGrid.innerHTML = `
      <div class="no-images-message" style="grid-column: 1 / -1;">
        <div class="no-images-icon"><i class="fas fa-question"></i></div>
        <h3>Error</h3>
        <p>No folder data available. Please try refreshing the preview.</p>
      </div>
    `;
    return;
  }
  imageGrid.innerHTML = `
    <div class="loading-spinner" style="grid-column: 1 / -1;">
      <div class="spinner"></div>
    </div>
  `;
  try {
    const parts = folderKey.split('-');
    const folderType = parts[0];
    const parentIndex = parseInt(parts[1]);
    const nestedIndex = parts[2] ? parseInt(parts[2]) : null;
    let folderPath;
    let folderName;
    if (parentIndex < 0 || parentIndex >= currentPreviewData.subfolders.length) {
      throw new Error(`Invalid parent folder index: ${parentIndex}`);
    }
    if (folderType === 'main') {
      const subfolder = currentPreviewData.subfolders[parentIndex];
      folderPath = subfolder.path;
      folderName = subfolder.name;
    } else if (folderType === 'nested') {
      const parentSubfolder = currentPreviewData.subfolders[parentIndex];
      if (!parentSubfolder.nested_folders || nestedIndex < 0 || nestedIndex >= parentSubfolder.nested_folders.length) {
        throw new Error(`Invalid nested folder index: ${nestedIndex}`);
      }
      const nestedFolder = parentSubfolder.nested_folders[nestedIndex];
      folderPath = nestedFolder.path;
      folderName = `${parentSubfolder.name} > ${nestedFolder.name}`;
    } else {
      throw new Error(`Invalid folder type: ${folderType}`);
    }
 console.log('Loading images from:', folderPath);
    const response = await fetch(`/get-folder-images/?folder_path=${encodeURIComponent(folderPath)}`);
    const result = await response.json();
    if (result.status === 'success') {
      displayImages(result.images, folderName);
    } else {
      imageGrid.innerHTML = `
        <div class="no-images-message" style="grid-column: 1 / -1;">
          <div class="no-images-icon"><i class="fas fa-image"></i></div>
          <h3>Error Loading Images</h3>
          <p>${result.message}</p>
        </div>
      `;
    }
  } catch (error) {
 console.error('Error loading folder images:', error);
    imageGrid.innerHTML = `
      <div class="no-images-message" style="grid-column: 1 / -1;">
        <div class="no-images-icon"><i class="fas fa-question"></i></div>
        <h3>Error Loading Images</h3>
        <p>${error.message}</p>
      </div>
    `;
  }
}

function displayImages(images, folderName) {
  const imageGrid = document.getElementById('image-grid');
  currentFolderImages = images;
  currentPage = 1;
  totalPages = Math.ceil(images.length / IMAGES_PER_PAGE);
  if (images.length === 0) {
    imageGrid.innerHTML = `
      <div class="no-images-message" style="grid-column: 1 / -1;">
        <div class="no-images-icon">No Images</div>
        <h3>No Images Found</h3>
        <p>No images found in ${folderName}</p>
      </div>
    `;
    return;
  }
  displayImagePage(images, 1, folderName);
}
function displayImagePage(images, page, folderName) {
  const imageGrid = document.getElementById('image-grid');
  const startIndex = (page - 1) * IMAGES_PER_PAGE;
  const endIndex = Math.min(startIndex + IMAGES_PER_PAGE, images.length);
  const pageImages = images.slice(startIndex, endIndex);
 console.log(`Displaying page ${page}/${totalPages}: images ${startIndex + 1}-${endIndex} of ${images.length}`);
  const imageCards = pageImages.map((image, localIndex) => {
    const globalIndex = startIndex + localIndex;
    return `
      <div class="image-card"
           onclick="openImageViewer(${globalIndex})"
           onmouseenter="preloadFullSizeOnHover('${image.path.replace(/'/g, "\\'")}')">
        ${image.is_label ? '<div class="label-badge">Label</div>' : ''}
        <div class="image-container">
          <img class="image-preview lazy-load"
               data-src="/serve-image/?image_path=${encodeURIComponent(image.path)}"
               data-index="${globalIndex}"
               alt="${image.name}"
               loading="lazy">
          <div class="image-placeholder">
            <div class="spinner"></div>
            <div class="loading-text">Loading...</div>
          </div>
        </div>
        <div class="image-info">
          <div class="image-name">${image.name}</div>
          <div class="image-details">
            <span>${formatFileSize(image.size)}</span>
            <span>${image.is_label ? 'Label' : 'Image'}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');
  let paginationHTML = '';
  if (totalPages > 1) {
    paginationHTML = `
      <div class="pagination-controls" style="grid-column: 1 / -1; display: flex; justify-content: center; align-items: center; gap: 15px; margin: 20px 0; padding: 15px; background: rgba(255,255,255,0.9); border-radius: 10px;">
        <button onclick="changeImagePage(-1)" ${currentPage <= 1 ? 'disabled' : ''} class="pagination-btn">← Previous</button>
        <span class="pagination-info">Page ${currentPage} of ${totalPages} (${startIndex + 1}-${endIndex} of ${images.length} images)</span>
        <button onclick="changeImagePage(1)" ${currentPage >= totalPages ? 'disabled' : ''} class="pagination-btn">Next →</button>
      </div>
    `;
  }
  imageGrid.innerHTML = imageCards + paginationHTML;
  initializeLazyLoading();
  const firstFewImages = pageImages.slice(0, PRELOAD_BATCH_SIZE).map(img => img.path);
  preloadImages(firstFewImages, MAX_CONCURRENT_LOADS, THUMBNAIL_SIZE, 75);
}
function changeImagePage(direction) {
  const newPage = currentPage + direction;
  if (newPage >= 1 && newPage <= totalPages && currentFolderImages.length > 0) {
    currentPage = newPage;
    displayImagePage(currentFolderImages, currentPage, 'Current Folder');
  }
}

function clearImageGrid() {
  const imageGrid = document.getElementById('image-grid');
  imageGrid.innerHTML = `
    <div class="no-images-message" style="grid-column: 1 / -1;">
      <div class="no-images-icon">No Images</div>
      <h3>Select a Folder</h3>
      <p>Choose a folder from the dropdown to view its images</p>
    </div>
  `;
}

function showImagePreview(runFolder = null) {
  const modal = document.getElementById('imagePreviewModal');
  if (runFolder) {
    const runNumberElement = document.getElementById('preview-run-number');
    const runNumberValue = document.getElementById('preview-run-number-value');
    if (runNumberElement && runNumberValue) {
      runNumberValue.textContent = runFolder;
      runNumberElement.style.display = 'inline-block';
    }
  }
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeImagePreview() {
  const modal = document.getElementById('imagePreviewModal');
  modal.classList.remove('show');
  document.body.style.overflow = 'auto';
  clearImageGrid();
}

function openImageViewer(imageIndex) {
  if (!currentFolderImages || currentFolderImages.length === 0) {
 console.error('No images available for viewing');
    return;
  }
  currentImageIndex = imageIndex;
  const currentImage = currentFolderImages[imageIndex];
  currentRotation = imageRotations[currentImage.path] || 0;
  showImageAtIndex(currentImageIndex);
  const modal = document.getElementById('imageViewerModal');
  modal.classList.add('show');
}

function showImageAtIndex(index) {
  if (!currentFolderImages || index < 0 || index >= currentFolderImages.length) {
    return;
  }
  const image = currentFolderImages[index];
  const imgElement = document.getElementById('viewer-image');
  const title = document.getElementById('viewer-title');
  const prevBtn = document.getElementById('viewer-prev-btn');
  const nextBtn = document.getElementById('viewer-next-btn');
  const cacheBuster = new Date().getTime();
  const randomId = Math.random().toString(36).substr(2, 9);
  imgElement.src = `/serve-image/?image_path=${encodeURIComponent(image.path)}&size=${FULL_SIZE}&quality=90&t=${cacheBuster}&r=${randomId}&v=${Math.random()}`;
  title.textContent = `${image.name} (${index + 1} of ${currentFolderImages.length})`;
  applyRotation();
  prevBtn.disabled = (index === 0);
  nextBtn.disabled = (index === currentFolderImages.length - 1);
}

function navigateImage(direction) {
  const newIndex = currentImageIndex + direction;
  if (newIndex >= 0 && newIndex < currentFolderImages.length) {
    currentImageIndex = newIndex;
    const currentImage = currentFolderImages[currentImageIndex];
    currentRotation = imageRotations[currentImage.path] || 0;
    showImageAtIndex(currentImageIndex);
  }
}

async function rotateImage(degrees) {
  const currentImage = currentFolderImages[currentImageIndex];
  if (!currentImage) {
 console.error('No current image for rotation');
    return;
  }
  const imagePath = currentImage.path;
  imageRotations[imagePath] = (imageRotations[imagePath] || 0) + degrees;
  if (imageRotations[imagePath] < 0) {
    imageRotations[imagePath] += 360;
  }
  imageRotations[imagePath] = imageRotations[imagePath] % 360;
  currentRotation = imageRotations[imagePath];
  applyRotation();
 console.log(`Rotating image ${currentImage.name} by ${degrees} degrees...`);
  const leftBtn = document.getElementById('viewer-rotate-left');
  const rightBtn = document.getElementById('viewer-rotate-right');
  if (leftBtn) leftBtn.disabled = true;
  if (rightBtn) rightBtn.disabled = true;
  try {
    const response = await fetch('/rotate-image/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        image_path: imagePath,
        degrees: degrees > 0 ? degrees : 360 + degrees
      })
    });
    const result = await response.json();
    if (result.status === 'success') {
 console.log(`Image rotated successfully: ${result.message}`);
      imageRotations[imagePath] = 0;
      currentRotation = 0;
      const imgElement = document.getElementById('viewer-image');
      if (imgElement) {
        imgElement.style.transform = 'rotate(0deg)';
         const cacheBuster = new Date().getTime();
         const randomId = Math.random().toString(36).substr(2, 9);
         const rotationId = Math.random().toString(36).substr(2, 9);
         imgElement.src = '';
         setTimeout(() => {
           const newSrc = `/serve-image/?image_path=${encodeURIComponent(imagePath)}&size=full&quality=90&t=${cacheBuster}&r=${randomId}&rot=${rotationId}&v=${Math.random()}`;
           imgElement.src = newSrc;
           imgElement.style.display = 'none';
           imgElement.offsetHeight;
           imgElement.style.display = 'block';
 console.log(`Image reloaded with aggressive cache-buster: ${cacheBuster}`);
         }, 50);
      }
    } else {
 console.error(' Error rotating image:', result.message);
      alert('Error rotating image: ' + result.message);
      imageRotations[imagePath] = (imageRotations[imagePath] || 0) - degrees;
      if (imageRotations[imagePath] < 0) {
        imageRotations[imagePath] += 360;
      }
      imageRotations[imagePath] = imageRotations[imagePath] % 360;
      currentRotation = imageRotations[imagePath];
      applyRotation();
    }
  } catch (error) {
 console.error(' Error calling rotation API:', error);
    alert('Error rotating image: ' + error.message);
    imageRotations[imagePath] = (imageRotations[imagePath] || 0) - degrees;
    if (imageRotations[imagePath] < 0) {
      imageRotations[imagePath] += 360;
    }
    imageRotations[imagePath] = imageRotations[imagePath] % 360;
    currentRotation = imageRotations[imagePath];
    applyRotation();
  } finally {
    if (leftBtn) leftBtn.disabled = false;
    if (rightBtn) rightBtn.disabled = false;
  }
}

function applyRotation() {
  const imgElement = document.getElementById('viewer-image');
  if (imgElement) {
    imgElement.style.transform = `rotate(${currentRotation}deg)`;
    imgElement.style.transition = 'transform 0.3s ease';
  }
}

function closeImageViewer() {
  const modal = document.getElementById('imageViewerModal');
  modal.classList.remove('show');
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

document.getElementById('imagePreviewModal').addEventListener('click', function(e) {
  if (e.target === this) {
    closeImagePreview();
  }
});

document.getElementById('imageViewerModal').addEventListener('click', function(e) {
  if (e.target === this) {
    closeImageViewer();
  }
});

document.addEventListener('keydown', function(e) {
  const previewModal = document.getElementById('imagePreviewModal');
  const viewerModal = document.getElementById('imageViewerModal');
  const confirmModal = document.getElementById('confirmationModal');
  if (e.key === 'Escape') {
    if (viewerModal.classList.contains('show')) {
      closeImageViewer();
    } else if (previewModal.classList.contains('show')) {
      closeImagePreview();
    } else if (confirmModal.classList.contains('show')) {
      closeConfirmationModal();
    }
  }
  if (viewerModal.classList.contains('show')) {
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      navigateImage(-1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      navigateImage(1);
    } else if (e.key === 'r' || e.key === 'R') {
      e.preventDefault();
      rotateImage(90);
    } else if (e.key === 'l' || e.key === 'L') {
      e.preventDefault();
      rotateImage(-90);
    }
  }
});

function getCsrfToken() {
  const csrfCookie = document.cookie.split(';')
    .find(cookie => cookie.trim().startsWith('csrftoken='));
  const token = csrfCookie ? csrfCookie.split('=')[1] : '';
 console.log('[DEBUG] CSRF Token:', token? 'Found': 'NOT FOUND', token);
  return token;
}
window.testCsrfToken = function() {
  const token = getCsrfToken();
 console.log('CSRF Token test:');
 console.log('- Token exists:',!!token);
 console.log('- Token length:', token.length);
 console.log('- All cookies:', document.cookie);
  return token;
};
window.debugStitchingFlow = function() {
 console.log('=== COMPLETE STITCHING FLOW DEBUG ===');
  const stitchButton = document.getElementById('uploadToStitcher');
 console.log('1. Stitch Images Button:');
 console.log('- Exists:',!!stitchButton);
 console.log('- Disabled:', stitchButton? stitchButton.disabled: 'N/A');
 console.log('- Has onclick:', stitchButton?!!stitchButton.onclick: 'N/A');
 console.log('2. Modal Data:');
 console.log('- window.modalSubfolders:',!!window.modalSubfolders);
 console.log('- window.totalSelectableItems:', typeof window.totalSelectableItems);
  const checkboxes = document.querySelectorAll('[id^="folder-checkbox-"]');
 console.log('3. Checkboxes:');
 console.log('- Count in DOM:', checkboxes.length);
 console.log('- Checked count:', document.querySelectorAll('[id^="folder-checkbox-"]:checked').length);
 console.log('4. CSRF Token:');
  const token = getCsrfToken();
 console.log('- Exists:',!!token);
  const runSelect = document.getElementById('run-folder-select');
 console.log('5. Run Folder Selection:');
 console.log('- Element exists:',!!runSelect);
 console.log('- Selected value:', runSelect? runSelect.value: 'N/A');
 console.log('=== END DEBUG ===');
};
window.testStitchingProcess = function() {
 console.log('=== MANUAL STITCHING TEST ===');
  if (!window.modalSubfolders || window.modalSubfolders.length === 0) {
 console.error(' No modal subfolders data. Please click "Stitch Images" first to populate the modal.');
    return;
  }
  if (typeof window.totalSelectableItems === 'undefined') {
 console.error(' No totalSelectableItems. Please click "Stitch Images" first to populate the modal.');
    return;
  }
 console.log('Modal data exists, manually triggering stitching process...');
  startStitchingProcess();
};
 console.log('testStitchingProcess function defined:', typeof window.testStitchingProcess);


function showFolderManagement() {
  const modal = document.getElementById('folderManagementModal');
  modal.classList.add('show');
  document.body.style.overflow = 'hidden';
  loadFolderMgmtRunFolders();
}

function closeFolderManagement() {
  const modal = document.getElementById('folderManagementModal');
  modal.classList.remove('show');
  document.body.style.overflow = 'auto';
  const folderList = document.getElementById('folder-management-list');
  folderList.innerHTML = `
    <div class="no-folders-message">
      <div class="no-images-icon"><i class="fas fa-folder"></i></div>
      <h3>Select a Run Folder</h3>
      <p>Choose a run folder from the dropdown to manage its subfolders</p>
    </div>
  `;
  const runSelect = document.getElementById('folder-mgmt-run-select');
  runSelect.value = '';
  runSelect.innerHTML = '<option value="">Loading run folders...</option>';
  window.currentFolderManagementData = null;
}

async function loadFolderMgmtRunFolders() {
  try {
    const response = await fetch('/get-all-runs/');
    const result = await response.json();
    if (result.status === 'success') {
      const select = document.getElementById('folder-mgmt-run-select');
      select.innerHTML = '<option value="">Select a run folder...</option>';
      const sortedRunFolders = result.run_folders.sort((a, b) => {
        const aNum = parseInt(a.name.replace('run_', ''));
        const bNum = parseInt(b.name.replace('run_', ''));
        return bNum - aNum;
      });
      sortedRunFolders.forEach(runFolder => {
        const option = document.createElement('option');
        option.value = runFolder.name;
        option.textContent = `${runFolder.name} (${runFolder.subfolder_count} folders)`;
        select.appendChild(option);
      });
    } else {
 console.error('Failed to load run folders:', result.message);
      const select = document.getElementById('folder-mgmt-run-select');
      select.innerHTML = '<option value="">Error loading run folders</option>';
    }
  } catch (error) {
 console.error('Error loading run folders:', error);
    const select = document.getElementById('folder-mgmt-run-select');
    select.innerHTML = '<option value="">Error loading run folders</option>';
  }
}

async function onFolderMgmtRunChange() {
  const select = document.getElementById('folder-mgmt-run-select');
  const selectedRun = select.value;
  if (!selectedRun) {
    const folderList = document.getElementById('folder-management-list');
    folderList.innerHTML = `
      <div class="no-folders-message">
        <div class="no-images-icon"><i class="fas fa-folder"></i></div>
        <h3>Select a Run Folder</h3>
        <p>Choose a run folder from the dropdown to manage its subfolders</p>
      </div>
    `;
    return;
  }
  const folderList = document.getElementById('folder-management-list');
  folderList.innerHTML = `
    <div class="folder-management-loading">
      <div class="spinner"></div>
      <div>Loading folder data for ${selectedRun}...</div>
    </div>
  `;
  try {
    const response = await fetch(`/get-folder-management-data/?run_folder=${selectedRun}`);
    const result = await response.json();
    if (result.status === 'success') {
      window.currentFolderManagementData = result;
      displayFolderManagementList(result.folders);
    } else {
      folderList.innerHTML = `
        <div class="folder-management-error">
          <div class="no-images-icon">⚠️</div>
          <h3>Error Loading Folders</h3>
          <p>${result.message}</p>
        </div>
      `;
    }
  } catch (error) {
 console.error('Error loading folder data:', error);
    folderList.innerHTML = `
      <div class="folder-management-error">
        <div class="no-images-icon">⚠️</div>
        <h3>Error Loading Folders</h3>
        <p>Failed to load folder data: ${error.message}</p>
      </div>
    `;
  }
}

function displayFolderManagementList(folders) {
  const folderList = document.getElementById('folder-management-list');
  if (!folders || folders.length === 0) {
    folderList.innerHTML = `
      <div class="no-folders-message">
        <div class="no-images-icon"><i class="fas fa-folder"></i></div>
        <h3>No Folders Found</h3>
        <p>This run folder doesn't contain any subfolders</p>
      </div>
    `;
    return;
  }
  let html = '';
  folders.forEach((folder, index) => {
    html += `
      <div class="folder-management-item" id="folder-item-${index}">
        <div class="folder-info-section">
          <div class="folder-name-display" id="folder-name-${index}">${folder.name}</div>
          <div class="folder-path-display">${folder.path}</div>
        </div>
        <div class="folder-actions">
          <button class="rename-btn" onclick="startRenameFolder(${index}, '${folder.path}', '${folder.name}')">
            <i class="fas fa-edit"></i> Rename
          </button>
        </div>
      </div>
    `;
    if (folder.nested_folders && folder.nested_folders.length > 0) {
      folder.nested_folders.forEach((nestedFolder, nestedIndex) => {
        const nestedItemIndex = `${index}-${nestedIndex}`;
        html += `
          <div class="folder-management-item nested-folder-item" id="folder-item-${nestedItemIndex}">
            <div class="folder-info-section">
              <div class="folder-name-display" id="folder-name-${nestedItemIndex}">${nestedFolder.name}</div>
              <div class="folder-path-display">${nestedFolder.path}</div>
            </div>
            <div class="folder-actions">
              <button class="rename-btn" onclick="startRenameFolder('${nestedItemIndex}', '${nestedFolder.path}', '${nestedFolder.name}')">
                <i class="fas fa-edit"></i> Rename
              </button>
            </div>
          </div>
        `;
      });
    }
  });
  folderList.innerHTML = html;
}

function startRenameFolder(itemIndex, folderPath, currentName) {
  const folderItem = document.getElementById(`folder-item-${itemIndex}`);
  const folderNameDisplay = document.getElementById(`folder-name-${itemIndex}`);
  const folderActions = folderItem.querySelector('.folder-actions');
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'rename-input';
  input.value = currentName;
  input.id = `rename-input-${itemIndex}`;
  const saveBtn = document.createElement('button');
  saveBtn.className = 'save-btn';
  saveBtn.innerHTML = '<i class="fas fa-save"></i> Save';
  saveBtn.onclick = () => saveRenameFolder(itemIndex, folderPath, input.value);
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'cancel-btn';
  cancelBtn.innerHTML = '<i class="fas fa-times"></i> Cancel';
  cancelBtn.onclick = () => cancelRenameFolder(itemIndex, folderPath, currentName);
  folderNameDisplay.style.display = 'none';
  folderActions.innerHTML = '';
  folderActions.appendChild(input);
  folderActions.appendChild(saveBtn);
  folderActions.appendChild(cancelBtn);
  input.focus();
  input.select();
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      saveRenameFolder(itemIndex, folderPath, input.value);
    } else if (e.key === 'Escape') {
      cancelRenameFolder(itemIndex, folderPath, currentName);
    }
  });
}

function cancelRenameFolder(itemIndex, folderPath, originalName) {
  const folderItem = document.getElementById(`folder-item-${itemIndex}`);
  const folderNameDisplay = document.getElementById(`folder-name-${itemIndex}`);
  const folderActions = folderItem.querySelector('.folder-actions');
  folderNameDisplay.style.display = 'block';
  folderActions.innerHTML = `
    <button class="rename-btn" onclick="startRenameFolder('${itemIndex}', '${folderPath}', '${originalName}')">
      <i class="fas fa-edit"></i> Rename
    </button>
  `;
}

async function saveRenameFolder(itemIndex, oldPath, newName) {
  if (!newName || newName.trim() === '') {
    alert('Folder name cannot be empty');
    return;
  }
  if (!/^[a-zA-Z0-9_-]+$/.test(newName)) {
    alert('Folder name can only contain letters, numbers, underscores, and hyphens');
    return;
  }
  try {
    const response = await fetch('/rename-folder/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify({
        old_path: oldPath,
        new_name: newName.trim()
      })
    });
    const result = await response.json();
    if (result.status === 'success') {
      const folderNameDisplay = document.getElementById(`folder-name-${itemIndex}`);
      folderNameDisplay.textContent = newName.trim();
      const folderItem = document.getElementById(`folder-item-${itemIndex}`);
      const folderActions = folderItem.querySelector('.folder-actions');
      folderActions.innerHTML = `
        <button class="rename-btn" onclick="startRenameFolder('${itemIndex}', '${result.new_path}', '${newName.trim()}')">
          <i class="fas fa-edit"></i> Rename
        </button>
      `;
      showFolderMgmtMessage(`Folder renamed successfully to "${newName.trim()}"`, 'success');
      if (window.currentFolderManagementData) {
        const pathParts = oldPath.split('/');
        const folderName = pathParts[pathParts.length - 1];
        for (let folder of window.currentFolderManagementData.folders) {
          if (folder.name === folderName) {
            folder.name = newName.trim();
            folder.path = result.new_path;
            break;
          }
          if (folder.nested_folders) {
            for (let nestedFolder of folder.nested_folders) {
              if (nestedFolder.name === folderName) {
                nestedFolder.name = newName.trim();
                nestedFolder.path = result.new_path;
                break;
              }
            }
          }
        }
      }
    } else {
      alert(`Error renaming folder: ${result.message}`);
    }
  } catch (error) {
 console.error('Error renaming folder:', error);
    alert(`Error renaming folder: ${error.message}`);
  }
}

function showFolderMgmtMessage(message, type = 'info') {
  let messageEl = document.getElementById('folder-mgmt-message');
  if (!messageEl) {
    messageEl = document.createElement('div');
    messageEl.id = 'folder-mgmt-message';
    messageEl.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      padding: 15px 20px;
      border-radius: 8px;
      font-weight: 600;
      z-index: 10000;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      transition: all 0.3s ease;
    `;
    document.body.appendChild(messageEl);
  }
  messageEl.textContent = message;
  if (type === 'success') {
    messageEl.style.background = 'linear-gradient(135deg, #22c55e, #16a34a)';
    messageEl.style.color = 'white';
  } else if (type === 'error') {
    messageEl.style.background = 'linear-gradient(135deg, #dc3545, #c82333)';
    messageEl.style.color = 'white';
  } else {
    messageEl.style.background = 'linear-gradient(135deg, #4a7c59, #2d5016)';
    messageEl.style.color = 'white';
  }
  messageEl.style.opacity = '1';
  messageEl.style.transform = 'translateX(0)';
  setTimeout(() => {
    messageEl.style.opacity = '0';
    messageEl.style.transform = 'translateX(100%)';
    setTimeout(() => {
      if (messageEl.parentNode) {
        messageEl.parentNode.removeChild(messageEl);
      }
    }, 300);
  }, 3000);
}

document.getElementById('folderManagementModal').addEventListener('click', function(e) {
  if (e.target === this) {
    closeFolderManagement();
  }
});