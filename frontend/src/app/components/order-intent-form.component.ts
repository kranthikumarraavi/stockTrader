// Order intent form component
import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

export interface OrderIntentData {
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
  order_type: 'market' | 'limit';
  limit_price?: number;
  option_type?: 'CE' | 'PE' | '';
  strike?: number;
  expiry?: string;
  strategy?: 'single' | 'vertical_spread' | 'iron_condor' | 'covered_call';
}

@Component({
  selector: 'app-order-intent-form',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './order-intent-form.component.html',
  styleUrl: './order-intent-form.component.scss'
})
export class OrderIntentFormComponent {
  @Output() intentSubmit = new EventEmitter<OrderIntentData>();

  form: OrderIntentData = {
    ticker: '',
    side: 'buy',
    quantity: 1,
    order_type: 'market',
    strategy: 'single',
    option_type: '',
  };

  submit(): void {
    this.intentSubmit.emit({ ...this.form });
  }
}
