(function () {
    var root = document.documentElement;
    var STORAGE_KEY = 'site-theme';

    function applyTheme(theme) {
        if (theme === 'dark') {
            root.setAttribute('data-theme', 'dark');
        } else {
            root.removeAttribute('data-theme');
            theme = 'light';
        }

        var toggles = document.querySelectorAll('[data-theme-toggle]');
        toggles.forEach(function (button) {
            button.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
            button.setAttribute('aria-label', 'Switch to ' + (theme === 'dark' ? 'light' : 'dark') + ' mode');
        });
    }

    function savedTheme() {
        var stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'dark' || stored === 'light') {
            return stored;
        }
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    document.addEventListener('DOMContentLoaded', function () {
        var currentTheme = savedTheme();
        applyTheme(currentTheme);

        document.querySelectorAll('[data-theme-toggle]').forEach(function (button) {
            button.addEventListener('click', function () {
                currentTheme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
                localStorage.setItem(STORAGE_KEY, currentTheme);
                applyTheme(currentTheme);
            });
        });
    });
})();
