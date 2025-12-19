# CodePost R Plot Capture Wrapper
local({
    # Create a temp dir for plots
    plot_dir <- tempfile()
    dir.create(plot_dir)
    plot_pattern <- file.path(plot_dir, "plot_%03d.png")
    
    # Open PNG device with pattern for multiple pages
    png(plot_pattern, width = 800, height = 600)

    tryCatch({
        # Execute student code with auto-printing enabled
        # This ensures all top-level ggplot calls are rendered
        source("student.R", print.eval = TRUE, echo = FALSE)
        
    }, finally = {
        # Close device
        dev.off()
        
        # List all generated plot files
        plot_files <- list.files(plot_dir, pattern = "plot_\\d+\\.png", full.names = TRUE)
        # Sort to ensure order
        plot_files <- sort(plot_files)
        
        if (length(plot_files) > 0) {
            if (requireNamespace("base64enc", quietly = TRUE)) {
                for (p_file in plot_files) {
                   if (file.info(p_file)$size > 1000) {
                       raw_data <- readBin(p_file, "raw", n = file.info(p_file)$size)
                       encoded <- base64enc::base64encode(raw_data)
                       cat(paste0("\n<<<CODEPOST_PLOT: ", encoded, " >>>\n"))
                   }
                }
            } else {
                message("[CodePost] Plots generated but 'base64enc' package missing. Cannot capture.")
            }
        }
        
        # Cleanup
        unlink(plot_dir, recursive = TRUE)
    })
})
