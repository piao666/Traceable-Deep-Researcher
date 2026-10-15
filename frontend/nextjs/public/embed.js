(function () {
    const script = document.currentScript;
    const appUrl = new URL(script.dataset.appUrl || "/", script.src);
    window.TraceableDeepResearcher = {
        init: function () {
            const parentApiUrl = localStorage.getItem("TDR_API_URL");

            // Create container
            const container = document.createElement("div");
            container.id = "traceable-deep-researcher-container";
            container.style.width = "100%";
            container.style.height = "100vh";
            container.style.overflow = "hidden"; // Hide scrollbar

            // Create iframe
            const iframe = document.createElement("iframe");
            const url = new URL(appUrl);
            if (parentApiUrl) url.searchParams.set("TDR_API_URL", parentApiUrl);
            iframe.src = url.href;
            iframe.title = "Traceable Deep Researcher";
            iframe.style.width = "100%";
            iframe.style.border = "none";
            iframe.style.height = "100%";
            iframe.style.overflow = "hidden";

            // Add custom styles to hide scrollbars
            const style = document.createElement("style");
            style.textContent = `
                #traceable-deep-researcher-container {
                    -ms-overflow-style: none;  /* IE and Edge */
                    scrollbar-width: none;     /* Firefox */
                }
                #traceable-deep-researcher-container::-webkit-scrollbar {
                    display: none;             /* Chrome, Safari and Opera */
                }
                #traceable-deep-researcher-container iframe {
                    -ms-overflow-style: none;
                    scrollbar-width: none;
                }
                #traceable-deep-researcher-container iframe::-webkit-scrollbar {
                    display: none;
                }
            `;
            document.head.appendChild(style);

            // Add iframe to container
            container.appendChild(iframe);
            script.parentNode.insertBefore(container, script);

            // Handle resize
            window.addEventListener("resize", () => {
                iframe.style.height = "100%";
            });

            // Ensure height is set after iframe loads
            iframe.addEventListener("load", () => {
                iframe.style.height = "100%";
            });
        },

        configure: function (options = {}) {
            if (options.height) {
                const iframe = document.querySelector("#traceable-deep-researcher-container iframe");
                if (iframe) {
                    iframe.style.height = options.height + "px";
                }
            }
        },
    };

    // Initialize when script loads
    window.TraceableDeepResearcher.init();
})();