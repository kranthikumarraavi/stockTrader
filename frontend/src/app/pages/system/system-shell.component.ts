import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-system-shell',
  standalone: true,
  imports: [RouterModule],
  templateUrl: './system-shell.component.html',
  styleUrl: './system-shell.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SystemShellComponent {}
