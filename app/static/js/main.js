// Main JS file for Asset Lookup

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Search autocomplete
    setupSearchAutocomplete();
    
    // File input custom styling
    setupFileInputs();
    
    // Tag management
    setupTagManagement();
});

// Search autocomplete
function setupSearchAutocomplete() {
    const searchInput = document.getElementById('navbarSearch');
    if (!searchInput) return;
    
    let searchTimeout;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        
        const query = this.value.trim();
        if (query.length < 2) return;
        
        searchTimeout = setTimeout(() => {
            fetch(`/api/search/assets?q=${encodeURIComponent(query)}`)
                .then(response => response.json())
                .then(data => {
                    const resultsDropdown = document.getElementById('searchResults');
                    resultsDropdown.innerHTML = '';
                    
                    if (data.length === 0) {
                        resultsDropdown.innerHTML = '<div class="dropdown-item text-muted">No results found</div>';
                        return;
                    }
                    
                    data.forEach(asset => {
                        const item = document.createElement('a');
                        item.href = `/assets/${asset.id}`;
                        item.className = 'dropdown-item';
                        
                        let statusBadge = '';
                        if (asset.status === 'Active') {
                            statusBadge = '<span class="badge bg-success ms-1">Active</span>';
                        } else if (asset.status === 'Expiring Soon') {
                            statusBadge = '<span class="badge bg-warning ms-1">Expiring Soon</span>';
                        } else {
                            statusBadge = '<span class="badge bg-danger ms-1">Expired</span>';
                        }
                        
                        item.innerHTML = `
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    <div class="fw-bold">${asset.name}</div>
                                    <div class="text-muted small">${asset.model}</div>
                                </div>
                                ${statusBadge}
                            </div>
                        `;
                        
                        resultsDropdown.appendChild(item);
                    });
                });
        }, 300);
    });
}

// File input styling
function setupFileInputs() {
    const fileInputs = document.querySelectorAll('.custom-file-input');
    fileInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const fileLabel = this.nextElementSibling;
            
            if (this.files && this.files.length > 1) {
                fileLabel.textContent = `${this.files.length} files selected`;
            } else if (this.files && this.files.length === 1) {
                fileLabel.textContent = this.files[0].name;
            } else {
                fileLabel.textContent = 'Choose file(s)';
            }
        });
    });
}

// Tag management
function setupTagManagement() {
    const tagForm = document.getElementById('tagForm');
    if (!tagForm) return;
    
    const tagNameInput = document.getElementById('tagName');
    const tagColorInput = document.getElementById('tagColor');
    const tagPreview = document.getElementById('tagPreview');
    
    // Update tag preview when inputs change
    tagNameInput.addEventListener('input', updateTagPreview);
    tagColorInput.addEventListener('input', updateTagPreview);
    
    function updateTagPreview() {
        tagPreview.textContent = tagNameInput.value || 'Tag Preview';
        tagPreview.style.backgroundColor = tagColorInput.value;
    }
}
