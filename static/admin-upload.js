(function () {
    function formatFileList(files) {
        if (!files || files.length === 0) {
            return 'No files selected';
        }

        var names = Array.prototype.map.call(files, function (file) {
            return file.name;
        });

        if (names.length <= 3) {
            return names.join(', ');
        }

        return names.slice(0, 3).join(', ') + ' +' + (names.length - 3) + ' more';
    }

    function wireDropzone(dropzone) {
        var input = dropzone.querySelector('[data-dropzone-input]');
        var label = dropzone.querySelector('[data-dropzone-files]');
        var preview = dropzone.querySelector('[data-dropzone-preview]');
        if (!input || !label) {
            return;
        }

        var defaultText = label.textContent;

        function renderPreview(files) {
            if (!preview) {
                return;
            }

            preview.innerHTML = '';
            Array.prototype.slice.call(files || []).forEach(function (file) {
                if (!file.type || file.type.indexOf('image/') !== 0) {
                    return;
                }

                var wrapper = document.createElement('div');
                wrapper.className = 'dropzone-thumb';

                var image = document.createElement('img');
                image.alt = file.name;

                var caption = document.createElement('span');
                caption.textContent = file.name;

                var reader = new FileReader();
                reader.onload = function (event) {
                    image.src = event.target.result;
                };
                reader.readAsDataURL(file);

                wrapper.appendChild(image);
                wrapper.appendChild(caption);
                preview.appendChild(wrapper);
            });
        }

        function renderFiles(files) {
            if (!files || files.length === 0) {
                label.textContent = defaultText;
                renderPreview([]);
                return;
            }
            label.textContent = formatFileList(files);
            renderPreview(files);
        }

        input.addEventListener('change', function () {
            renderFiles(input.files);
        });

        dropzone.addEventListener('dragenter', function (event) {
            event.preventDefault();
            dropzone.classList.add('is-dragover');
        });

        dropzone.addEventListener('dragover', function (event) {
            event.preventDefault();
            dropzone.classList.add('is-dragover');
        });

        dropzone.addEventListener('dragleave', function (event) {
            event.preventDefault();
            if (!dropzone.contains(event.relatedTarget)) {
                dropzone.classList.remove('is-dragover');
            }
        });

        dropzone.addEventListener('drop', function (event) {
            event.preventDefault();
            dropzone.classList.remove('is-dragover');
            var files = event.dataTransfer.files;
            if (!files || files.length === 0) {
                return;
            }

            input.files = files;
            renderFiles(files);
        });

        renderFiles(input.files);
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-dropzone]').forEach(wireDropzone);
    });
})();
