class IIIFDownloader {
    constructor() {
        this.currentSessionId = null;
        this.progressInterval = null;
        this.initializeElements();
        this.bindEvents();
    }

    initializeElements() {
        this.elements = {
            imageIdInput: document.getElementById('image-id'),
            downloadBtn: document.getElementById('download-btn'),
            cancelBtn: document.getElementById('cancel-btn'),
            retryBtn: document.getElementById('retry-btn'),
            newDownloadBtn: document.getElementById('new-download-btn'),
            downloadFileBtn: document.getElementById('download-file-btn'),
            
            inputSection: document.getElementById('input-section'),
            progressSection: document.getElementById('progress-section'),
            successSection: document.getElementById('success-section'),
            errorSection: document.getElementById('error-section'),
            
            progressBar: document.getElementById('progress-bar'),
            progressPercentage: document.getElementById('progress-percentage'),
            statusMessage: document.getElementById('status-message'),
            errorText: document.getElementById('error-text')
        };
    }

    bindEvents() {
        this.elements.downloadBtn.addEventListener('click', () => this.startDownload());
        this.elements.cancelBtn.addEventListener('click', () => this.cancelDownload());
        this.elements.retryBtn.addEventListener('click', () => this.resetToInput());
        this.elements.newDownloadBtn.addEventListener('click', () => this.resetToInput());
        this.elements.downloadFileBtn.addEventListener('click', () => this.downloadFile());
        
        // Enter key support
        this.elements.imageIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.startDownload();
            }
        });

        // Auto-focus input
        this.elements.imageIdInput.focus();
    }

    async startDownload() {
        const imageId = this.elements.imageIdInput.value.trim();
        
        if (!imageId) {
            this.showError('Please enter an IIIF image ID');
            return;
        }

        // Validate image ID format
        if (!/^[a-zA-Z0-9_-]+$/.test(imageId)) {
            this.showError('Invalid image ID format. Please provide a valid IIIF image ID.');
            return;
        }

        this.showProgress();
        
        try {
            const response = await fetch('/start_download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ image_id: imageId })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Failed to start download');
            }

            this.currentSessionId = data.session_id;
            this.startProgressPolling();

        } catch (error) {
            console.error('Download start error:', error);
            this.showError(error.message);
        }
    }

    startProgressPolling() {
        if (!this.currentSessionId) return;

        this.progressInterval = setInterval(async () => {
            try {
                const response = await fetch(`/progress/${this.currentSessionId}`);
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || 'Failed to get progress');
                }

                this.updateProgress(data);

                if (data.completed || data.error) {
                    clearInterval(this.progressInterval);
                    this.progressInterval = null;

                    if (data.completed) {
                        this.showSuccess();
                    } else if (data.error) {
                        this.showError(data.error);
                    }
                }

            } catch (error) {
                console.error('Progress polling error:', error);
                clearInterval(this.progressInterval);
                this.progressInterval = null;
                this.showError('Failed to track download progress');
            }
        }, 1000); // Poll every second
    }

    updateProgress(data) {
        const progress = data.progress || 0;
        const message = data.message || 'Processing...';

        this.elements.progressBar.style.width = `${progress}%`;
        this.elements.progressBar.setAttribute('aria-valuenow', progress);
        this.elements.progressPercentage.textContent = `${Math.round(progress)}%`;
        
        this.elements.statusMessage.innerHTML = `
            <i class="fas fa-spinner fa-spin me-2"></i>
            ${message}
        `;
    }

    cancelDownload() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
        this.currentSessionId = null;
        this.resetToInput();
    }

    downloadFile() {
        if (!this.currentSessionId) {
            this.showError('No file available for download');
            return;
        }

        // Create download link
        const link = document.createElement('a');
        link.href = `/download/${this.currentSessionId}`;
        link.download = ''; // Let server determine filename
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    showProgress() {
        this.hideAllSections();
        this.elements.progressSection.classList.remove('d-none');
        this.updateProgress({ progress: 0, message: 'Starting download...' });
    }

    showSuccess() {
        this.hideAllSections();
        this.elements.successSection.classList.remove('d-none');
    }

    showError(message) {
        this.hideAllSections();
        this.elements.errorSection.classList.remove('d-none');
        this.elements.errorText.textContent = message;
        
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    }

    resetToInput() {
        this.hideAllSections();
        this.elements.inputSection.classList.remove('d-none');
        this.elements.imageIdInput.value = '';
        this.elements.imageIdInput.focus();
        
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
        
        this.currentSessionId = null;
    }

    hideAllSections() {
        this.elements.inputSection.classList.add('d-none');
        this.elements.progressSection.classList.add('d-none');
        this.elements.successSection.classList.add('d-none');
        this.elements.errorSection.classList.add('d-none');
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new IIIFDownloader();
});
