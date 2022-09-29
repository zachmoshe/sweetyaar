async function register() {
    if ("serviceWorker" in navigator) {
        try {
            registration = await navigator.serviceWorker.register("serviceworker.js")
        } catch (error) {
            console.log("ServiceWorker registration failed");
            console.log(error)
        }
    }
}
register();
