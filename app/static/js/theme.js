document.addEventListener("DOMContentLoaded", function () {
    const themeToggle = document.getElementById("themeToggle");

    if (!themeToggle) return;

    const savedTheme = localStorage.getItem("cems-theme");

    if (savedTheme === "dark") {
        document.documentElement.classList.add("dark");
    } else if (savedTheme === "light") {
        document.documentElement.classList.remove("dark");
    }

    function updateThemeButton() {
        const isDark = document.documentElement.classList.contains("dark");
        const label = isDark ? "Switch to light mode" : "Switch to dark mode";

        themeToggle.setAttribute("aria-label", label);
        themeToggle.setAttribute("aria-pressed", isDark ? "true" : "false");
        themeToggle.setAttribute("title", label);
    }

    updateThemeButton();

    themeToggle.addEventListener("click", function () {
        const isDark = document.documentElement.classList.toggle("dark");

        localStorage.setItem("cems-theme", isDark ? "dark" : "light");
        updateThemeButton();
    });
});
