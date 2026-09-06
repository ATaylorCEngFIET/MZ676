// Verilog-2001 example: non-ANSI ports and nonblocking pipeline assignments.
module legacy_pipeline(CLK, D, Q);
  input CLK;
  input [7:0] D;
  output [7:0] Q;
  reg [7:0] Stage1, Stage2;
  always @(posedge CLK) begin
    Stage1 <= D;
    Stage2 <= Stage1;
  end
  assign Q = Stage2;
endmodule
