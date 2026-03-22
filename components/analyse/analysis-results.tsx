              </div>
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 py-2">
              <Loader2 className="size-4 animate-spin text-primary" />
              <span className="text-xs text-muted-foreground">Recalculating...</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}