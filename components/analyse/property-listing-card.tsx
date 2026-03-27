"use client"

import { useState } from "react"
import { X, ExternalLink, ChevronLeft, ChevronRight } from "lucide-react"

export interface ScrapedListing {
  address: string
  postcode?: string
  price?: number
  propertyType?: string
  bedrooms?: number
  bathrooms?: number
  sqft?: number
  sqm?: number
  tenureType?: string
  leaseYears?: number
  keyFeatures?: string[]
  description?: string
  images?: string[]
  floorplans?: string[]
  agentName?: string
  agentPhone?: string
  agentAddress?: string
  listingUrl?: string
  source?: "rightmove" | "onthemarket" | string
}

function formatPrice(price?: number) {
  if (!price) return null
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: 0 }).format(price)
}

function SourceLabel({ source }: { source?: string }) {
  if (!source) return null
  const label = source === "rightmove" ? "Rightmove" : source === "onthemarket" ? "OnTheMarket" : source
  return (
    <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
      {label}
    </span>
  )
}

function ImageGallery({ images, floorplans }: { images?: string[]; floorplans?: string[] }) {
  const [galleryIdx, setGalleryIdx] = useState(0)
  const allImages = [...(images || []), ...(floorplans || [])]
  const isFloorplan = (idx: number) => idx >= (images?.length ?? 0)

  if (allImages.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      {/* Main image */}
      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={allImages[galleryIdx]}
          alt={isFloorplan(galleryIdx) ? "Floor plan" : `Property image ${galleryIdx + 1}`}
          className="h-full w-full object-cover"
          onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
        />
        {isFloorplan(galleryIdx) && (
          <div className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
            Floor Plan
          </div>
        )}
        {allImages.length > 1 && (
          <>
            <button
              onClick={() => setGalleryIdx((i) => (i - 1 + allImages.length) % allImages.length)}
              className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-1 text-white hover:bg-black/70"
              aria-label="Previous image"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              onClick={() => setGalleryIdx((i) => (i + 1) % allImages.length)}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-1 text-white hover:bg-black/70"
              aria-label="Next image"
            >
              <ChevronRight className="size-4" />
            </button>
            <div className="absolute bottom-2 right-2 rounded bg-black/50 px-2 py-0.5 text-xs text-white">
              {galleryIdx + 1} / {allImages.length}
            </div>
          </>
        )}
      </div>
      {/* Thumbnail strip */}
      {allImages.length > 1 && (
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {allImages.map((src, idx) => (
            <button
              key={idx}
              onClick={() => setGalleryIdx(idx)}
              className={`relative h-14 w-20 shrink-0 overflow-hidden rounded border-2 transition-all ${
                idx === galleryIdx ? "border-primary" : "border-transparent opacity-60 hover:opacity-80"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={isFloorplan(idx) ? "Floor plan thumb" : `Thumb ${idx + 1}`}
                className="h-full w-full object-cover"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
              />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ListingModal({ listing, onClose }: { listing: ScrapedListing; onClose: () => void }) {
  const sourceLabel = listing.source === "rightmove" ? "Rightmove" : listing.source === "onthemarket" ? "OnTheMarket" : "Listing"

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-background shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-border/50 px-6 py-4">
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <SourceLabel source={listing.source} />
              {listing.price && (
                <span className="text-lg font-bold text-foreground">{formatPrice(listing.price)}</span>
              )}
            </div>
            <p className="text-sm text-muted-foreground truncate">{listing.address}</p>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-full p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto p-6 flex flex-col gap-6">
          {/* Image gallery */}
          <ImageGallery images={listing.images} floorplans={listing.floorplans} />

          {/* Key details grid */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
            {listing.propertyType && (
              <div><p className="text-xs text-muted-foreground">Property Type</p><p className="text-sm font-medium text-foreground">{listing.propertyType}</p></div>
            )}
            {listing.bedrooms != null && (
              <div><p className="text-xs text-muted-foreground">Bedrooms</p><p className="text-sm font-medium text-foreground">{listing.bedrooms}</p></div>
            )}
            {listing.bathrooms != null && (
              <div><p className="text-xs text-muted-foreground">Bathrooms</p><p className="text-sm font-medium text-foreground">{listing.bathrooms}</p></div>
            )}
            {listing.postcode && (
              <div><p className="text-xs text-muted-foreground">Postcode</p><p className="text-sm font-medium text-foreground">{listing.postcode}</p></div>
            )}
            {listing.tenureType && (
              <div>
                <p className="text-xs text-muted-foreground">Tenure</p>
                <p className="text-sm font-medium text-foreground capitalize">
                  {listing.tenureType}
                  {listing.leaseYears ? ` — ${listing.leaseYears} yrs remaining` : ""}
                </p>
              </div>
            )}
            {(listing.sqft || listing.sqm) && (
              <div>
                <p className="text-xs text-muted-foreground">Size</p>
                <p className="text-sm font-medium text-foreground">
                  {listing.sqft ? `${listing.sqft} sqft` : ""}
                  {listing.sqft && listing.sqm ? " / " : ""}
                  {listing.sqm ? `${listing.sqm} sqm` : ""}
                </p>
              </div>
            )}
          </div>

          {/* Key features */}
          {listing.keyFeatures && listing.keyFeatures.length > 0 && (
            <div className="flex flex-col gap-2">
              <h4 className="text-sm font-semibold text-foreground">Key Features</h4>
              <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                {listing.keyFeatures.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                    <span className="mt-1 size-1.5 shrink-0 rounded-full bg-primary" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Description */}
          {listing.description && (
            <div className="flex flex-col gap-2">
              <h4 className="text-sm font-semibold text-foreground">Description</h4>
              <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">{listing.description}</p>
            </div>
          )}

          {/* Agent info */}
          {(listing.agentName || listing.agentPhone || listing.agentAddress) && (
            <div className="rounded-lg border border-border/50 bg-muted/30 px-4 py-3 flex flex-col gap-1">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Agent</h4>
              {listing.agentName && <p className="text-sm font-medium text-foreground">{listing.agentName}</p>}
              {listing.agentPhone && <p className="text-sm text-muted-foreground">{listing.agentPhone}</p>}
              {listing.agentAddress && <p className="text-sm text-muted-foreground">{listing.agentAddress}</p>}
            </div>
          )}

          {/* View on source link */}
          {listing.listingUrl && (
            <a
              href={listing.listingUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm font-medium text-primary hover:underline"
            >
              <ExternalLink className="size-4" />
              View on {sourceLabel}
            </a>
          )}
        </div>
      </div>
    </div>
  )
}

interface PropertyListingCardProps {
  listing: ScrapedListing
}

export function PropertyListingCard({ listing }: PropertyListingCardProps) {
  const [isOpen, setIsOpen] = useState(false)
  const thumbnail = listing.images?.[0]

  return (
    <>
      {/* Collapsed card — full card is clickable */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="group flex w-full items-center gap-4 rounded-xl border border-border/50 bg-card p-3 text-left shadow-sm transition-all hover:border-primary/40 hover:shadow-md"
      >
        {/* Thumbnail */}
        <div className="relative size-16 shrink-0 overflow-hidden rounded-lg bg-muted sm:size-20">
          {thumbnail ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumbnail}
              alt="Property thumbnail"
              className="h-full w-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">No image</div>
          )}
        </div>

        {/* Info */}
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <SourceLabel source={listing.source} />
            {listing.price && (
              <span className="text-base font-bold text-foreground">{formatPrice(listing.price)}</span>
            )}
          </div>
          <p className="truncate text-sm text-foreground">{listing.address}</p>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            {listing.postcode && <span>{listing.postcode}</span>}
            {listing.propertyType && <span>· {listing.propertyType}</span>}
            {listing.bedrooms != null && <span>· {listing.bedrooms} bed</span>}
          </div>
        </div>

        <span className="shrink-0 text-xs text-primary group-hover:underline">View details →</span>
      </button>

      {/* Expanded modal */}
      {isOpen && (
        <ListingModal listing={listing} onClose={() => setIsOpen(false)} />
      )}
    </>
  )
}
