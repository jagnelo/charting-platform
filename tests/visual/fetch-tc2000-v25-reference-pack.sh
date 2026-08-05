#!/usr/bin/env bash

# Fetches permission-sensitive TC2000 reference media outside the repository.
# The downloaded images are for internal visual analysis only and are never
# copied into the application bundle. The generated index records each source
# URL and SHA-256 so a reviewer can replace, revoke, or re-verify the pack.

set -euo pipefail

output_dir="${TC2000_REFERENCE_DIR:-${TMPDIR:-/tmp}/tc2000-v25-reference-pack}"
pages_dir="$output_dir/pages"
media_dir="$output_dir/media"
index_file="$output_dir/media-index.tsv"

mkdir -p "$pages_dir" "$media_dir"

declare -a sources=(
  "pinning-columns|https://help.tc2000.com/m/125751/l/1916114-pinning-columns|official_v25_help"
  "factory-default-layout|https://help.tc2000.com/m/69401/l/743982-factory-default-layout-workspace|official_help_behavioral_history"
  "drag-value-column|https://help.tc2000.com/m/125751/l/1874609-how-to-drag-drop-a-value-column-to-a-chart|official_help_behavioral_history"
  "group-columns|https://help.tc2000.com/m/125751/l/1874601-how-to-group-columns|official_help_discovery"
  "stack-columns|https://help.tc2000.com/m/125751/l/1874595-how-to-stack-columns-in-a-watchlist|official_help_discovery"
  "market-gauge-understand|https://help.tc2000.com/m/125751/l/1874582-how-to-understand-a-market-gauge|official_help_discovery"
  "market-gauge-create|https://help.tc2000.com/m/125751/l/1687541-how-to-create-a-market-gauge|official_help_discovery"
  "data-grid-use|https://help.tc2000.com/m/125751/l/1874646-how-to-use-a-data-grid|official_help_discovery"
  "data-grid-create|https://help.tc2000.com/m/125751/l/1874647-how-to-create-a-data-grid|official_help_discovery"
  "data-grid-appearance|https://help.tc2000.com/m/69401/l/1678533-how-to-edit-how-a-data-grid-looks|official_help_behavioral_history"
  "comparison-chart|https://help.tc2000.com/m/125751/l/1874643-how-to-create-a-comparison-chart-from-multiple-symbols|official_help_discovery"
  "projection-space|https://help.tc2000.com/m/125751/l/1874606-how-to-create-projection-space-on-a-chart|official_help_discovery"
  "chart-timeframes|https://help.tc2000.com/m/125751/l/1874607-how-to-change-chart-timeframes|official_help_discovery"
  "floating-window|https://help.tc2000.com/m/125751/l/1874615-how-to-drag-items-to-a-floating-window|official_help_discovery"
  "reposition-tabs|https://help.tc2000.com/m/125751/l/1874614-how-to-drag-drop-tabs-to-reposition-in-a-tool-window|official_help_discovery"
  "notes-window|https://help.tc2000.com/m/125751/l/1874628-how-to-use-the-redesigned-news-or-notes-window-controls|official_help_discovery"
  "event-markers|https://help.tc2000.com/m/125751/l/1909214-managing-event-markers|official_v25_help"
  "past-performance|https://help.tc2000.com/m/125751/l/1909245-past-performance-lines|official_v25_help"
  "column-editor|https://help.tc2000.com/m/125751/l/1874588-how-to-use-the-column-editor|official_help_discovery"
)

printf 'source_id\tsource_type\tpage_url\tmedia_file\tmedia_url\tsha256\n' > "$index_file"

for source in "${sources[@]}"; do
  IFS='|' read -r source_id page_url source_type <<< "$source"
  page_file="$pages_dir/$source_id.html"
  curl --fail --location --silent --show-error --max-time 45 "$page_url" -o "$page_file"

  rg --no-filename -o \
    'https://media\.screensteps\.com/image_assets/assets/[^" ]+/original/[^" ]+\.(png|jpg|jpeg)' \
    "$page_file" | sort -u | while read -r media_url; do
      media_file="${media_url##*/}"
      media_path="$media_dir/$media_file"
      curl --fail --location --silent --show-error --max-time 45 "$media_url" -o "$media_path"
      sha256="$(shasum -a 256 "$media_path" | awk '{print $1}')"
      printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$source_id" "$source_type" "$page_url" "$media_file" "$media_url" "$sha256" >> "$index_file"
    done
done

# Official shared-layout preview images are served by a different endpoint than
# Help Site media. Keep them in the same controlled pack and index them with the
# originating layout page so the previews remain reproducible discovery evidence.
declare -a direct_media_sources=(
  "bulls-shared-layout|https://www.tc2000.com/share/affiliate/bulls/layout/7fe75a78-4faa-4f1d-8088-b4f4ff94b954|official_shared_layout|https://www.tc2000.com/util/ImageForExportedItem/7fe75a78-4faa-4f1d-8088-b4f4ff94b954?quality=low|bulls-shared-layout.png"
  "emmanuel-shared-layout|https://www.tc2000.com/share/el3470/layout/18fbc0d1-daa4-4260-8167-111a275d6dc1|official_shared_layout|https://www.tc2000.com/util/ImageForExportedItem/18fbc0d1-daa4-4260-8167-111a275d6dc1?quality=low|emmanuel-shared-layout.png"
  "official-version-25-product-image|https://www.tc2000.com/download/version|official_version_25_product_page|https://www.tc2000.com/CMS_Static/Uploads/6E7A586D453831/Flying_Laptop_Right_Mock_8bit.png|official-version-25-product-image.png"
)

for source in "${direct_media_sources[@]}"; do
  IFS='|' read -r source_id page_url source_type media_url media_file <<< "$source"
  media_path="$media_dir/$media_file"
  curl --fail --location --silent --show-error --max-time 45 "$media_url" -o "$media_path"
  sha256="$(shasum -a 256 "$media_path" | awk '{print $1}')"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$source_id" "$source_type" "$page_url" "$media_file" "$media_url" "$sha256" >> "$index_file"
done

printf 'Reference pack: %s\n' "$output_dir"
printf 'Media files: %s\n' "$(find "$media_dir" -type f | wc -l | tr -d ' ')"
printf 'Index: %s\n' "$index_file"
