// Ticker tape component
import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WatchlistItem } from '../services/live-stream.service';

@Component({
  selector: 'app-ticker-tape',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ticker-tape.component.html',
  styleUrl: './ticker-tape.component.scss'
})
export class TickerTapeComponent {
  @Input() items: WatchlistItem[] = [];

  get doubledItems(): WatchlistItem[] {
    // Duplicate for seamless infinite scroll
    return [...this.items, ...this.items];
  }
}